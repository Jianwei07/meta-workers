import sqlite3

from fastapi.testclient import TestClient

from meta_workers.runtime import ModelTurn
from meta_workers.tools import needs_approval
from test_chat import wait_for


class ApprovalModel:
    def __init__(self) -> None:
        self.called = False

    async def stream_turn(self, model, messages, tools, on_delta):
        if not self.called:
            self.called = True
            return ModelTurn("", [{
                "id": "tool_write",
                "type": "function",
                "function": {"name": "write_file", "arguments": '{"path":"notes.txt","content":"done"}'},
            }])
        return ModelTurn("File written.", [])


class MemorySandbox:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def write_file(self, user_id: str, path: str, content: bytes) -> None:
        self.files[f"{user_id}/{path}"] = content


def test_write_tool_waits_for_explicit_approval(client: TestClient):
    sandbox = MemorySandbox()
    client.app.state.runner.model = ApprovalModel()
    client.app.state.runner.sandbox = sandbox
    run_id = client.post(
        "/api/users/user_alice/agents/agent_alice_kyc/runs",
        json={"prompt": "Write a note.", "client_nonce": "nonce-0002"},
    ).json()["id"]

    def pending():
        with sqlite3.connect(client.app.state.settings.database_path) as connection:
            return connection.execute("SELECT id FROM tool_calls WHERE run_id = ? AND status = 'waiting'", (run_id,)).fetchone()

    approval_id = wait_for(pending)[0]
    snapshot = client.get("/api/users/user_alice/agents/agent_alice_kyc/thread").json()
    assert snapshot["pending_approval"]["tool"] == "write_file"
    assert client.post(f"/api/users/user_alice/runs/{run_id}/approvals/{approval_id}", json={"decision": "approve"}).status_code == 200
    wait_for(lambda: client.get("/api/users/user_alice/agents/agent_alice_kyc/thread").json()["active_run"] is None)
    assert sandbox.files == {"user_alice/notes.txt": b"done"}


def test_workspace_mode_still_prompts_before_public_egress():
    assert needs_approval("workspace", "execution") is False
    assert needs_approval("workspace", "egress") is True
