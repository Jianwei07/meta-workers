import asyncio
import json
import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient

from meta_workers.config import Settings
from meta_workers.runtime import OpenAIModel, function_calls, response_output_item, response_text_delta
from meta_workers.tools import tool_registry


def test_openai_settings_and_model_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_ALLOWLIST", raising=False)
    settings = Settings.from_env()
    assert settings.openai_api_key == "test-key"
    assert settings.default_model == "gpt-5.6"
    assert settings.allowed_models == ("gpt-5.6",)


def test_api_rejects_a_model_outside_the_allowlist(client: TestClient):
    response = client.patch(
        "/api/users/user_alice/agents/agent_alice_kyc",
        json={"model": "not-allowed"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MODEL_NOT_ALLOWED"


def test_responses_stream_helpers_and_tool_schema():
    assert response_text_delta(SimpleNamespace(type="response.output_text.delta", delta="hello")) == "hello"
    item = {
        "type": "function_call",
        "call_id": "call_1",
        "name": "read_file",
        "arguments": '{"path":"notes.txt"}',
    }
    output = response_output_item(
        SimpleNamespace(type="response.output_item.done", output_index=2, item=item)
    )
    assert output == (2, item)
    assert function_calls([{"type": "reasoning", "encrypted_content": "cipher"}, item]) == [item]
    schema = tool_registry()["read_file"].openai_schema()
    assert schema["type"] == "function" and schema["name"] == "read_file"
    assert "function" not in schema


def test_openai_model_streams_and_keeps_complete_output_items(tmp_path):
    class FakeResponses:
        async def create(self, **kwargs):
            self.kwargs = kwargs

            async def events():
                yield SimpleNamespace(type="response.output_text.delta", delta="Hello ")
                yield SimpleNamespace(type="response.output_text.delta", delta="world")
                yield SimpleNamespace(
                    type="response.output_item.done",
                    output_index=0,
                    item={"type": "reasoning", "id": "rs_1", "encrypted_content": "cipher"},
                )
                yield SimpleNamespace(
                    type="response.output_item.done",
                    output_index=1,
                    item={"type": "function_call", "call_id": "call_1", "name": "read_file", "arguments": "{}"},
                )

            return events()

    settings = Settings(tmp_path, "test-key", "gpt-5.6", ("gpt-5.6",), "sandbox", 30)
    model = OpenAIModel(settings)
    model.client = SimpleNamespace(responses=FakeResponses())
    deltas = []

    async def on_delta(delta):
        deltas.append(delta)

    async def run():
        return await model.stream_turn("gpt-5.6", [{"role": "user", "content": "Hi"}], [], on_delta)

    turn = asyncio.run(run())
    assert turn.content == "Hello world"
    assert turn.tool_calls == [turn.response_items[1]]
    assert model.client.responses.kwargs["store"] is False
    assert model.client.responses.kwargs["include"] == ["reasoning.encrypted_content"]


def test_stateless_history_replays_responses_and_legacy_rows(client: TestClient):
    response_items = [
        {"type": "reasoning", "id": "rs_1", "encrypted_content": "cipher"},
        {
            "type": "message",
            "id": "msg_1",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "New answer.", "annotations": []}],
        },
    ]
    legacy_calls = [{
        "id": "call_old",
        "type": "function",
        "function": {"name": "read_file", "arguments": '{"path":"old.txt"}'},
    }]
    with sqlite3.connect(client.app.state.settings.database_path) as connection:
        rows = [
            ("history_user", 1, "user", "Question", None, None, None),
            ("history_assistant", 2, "assistant", "Checking.", json.dumps(legacy_calls), None, None),
            ("history_tool", 3, "tool", '{"content":"old"}', None, "call_old", None),
            ("history_new", 4, "assistant", "New answer.", None, None, json.dumps(response_items)),
        ]
        connection.executemany(
            """
            INSERT INTO messages(id, user_id, thread_id, seq, role, content, tool_calls_json, tool_call_id, response_items_json)
            VALUES (?, 'user_alice', 'thread_alice_kyc', ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    items = asyncio.run(client.app.state.runner.model_messages({
        "user_id": "user_alice",
        "agent_id": "agent_alice_kyc",
        "agent_name": "KYC Research Agent",
        "instructions": "Research public companies.",
        "thread_id": "thread_alice_kyc",
    }))
    assert items[1:] == [
        {"role": "user", "content": "Question"},
        {"role": "assistant", "content": "Checking."},
        {"type": "function_call", "call_id": "call_old", "name": "read_file", "arguments": '{"path":"old.txt"}'},
        {"type": "function_call_output", "call_id": "call_old", "output": '{"content":"old"}'},
        *response_items,
    ]
