from fastapi.testclient import TestClient


def test_seeded_users_are_isolated(client: TestClient):
    assert [user["name"] for user in client.get("/api/users").json()] == ["Alice", "Bob"]
    assert client.get("/api/users/user_bob/agents/agent_alice_kyc/thread").status_code == 404
    assert client.get("/healthz").json()["database"] is True
