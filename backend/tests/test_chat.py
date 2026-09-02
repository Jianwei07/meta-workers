import sqlite3
import time
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from meta_workers.runtime import ModelTurn


def wait_for(check: Callable[[], Any], timeout: float = 2) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if value := check():
            return value
        time.sleep(0.01)
    raise AssertionError("background run did not reach the expected state")


class FinalModel:
    async def stream_turn(self, model, messages, tools, on_delta):
        await on_delta("Research ready.")
        return ModelTurn("Research ready.", [], [{
            "type": "message",
            "id": "msg_test",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "Research ready.", "annotations": []}],
        }])


def test_run_persists_and_duplicate_nonce_returns_same_run(client: TestClient):
    client.app.state.runner.model = FinalModel()
    body = {"prompt": "Research Acme using public sources.", "client_nonce": "nonce-0001"}
    first = client.post("/api/users/user_alice/agents/agent_alice_kyc/runs", json=body)
    run_id = first.json()["id"]
    wait_for(lambda: client.get("/api/users/user_alice/agents/agent_alice_kyc/thread").json()["active_run"] is None)
    duplicate = client.post("/api/users/user_alice/agents/agent_alice_kyc/runs", json=body)
    assert first.status_code == 202 and duplicate.json()["id"] == run_id
    messages = client.get("/api/users/user_alice/agents/agent_alice_kyc/thread").json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    with sqlite3.connect(client.app.state.settings.database_path) as connection:
        stored = connection.execute(
            "SELECT response_items_json FROM messages WHERE role = 'assistant'"
        ).fetchone()[0]
    assert '"id": "msg_test"' in stored
