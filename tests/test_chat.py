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
        return ModelTurn("Research ready.", [])


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
