from fastapi.testclient import TestClient


def test_publish_and_install_creates_an_independent_copy(client: TestClient):
    body = {"name": "source-check", "description": "Check source quality.", "instructions": "Prefer primary public sources."}
    draft = client.post("/api/users/user_alice/skills", json=body).json()
    client.post(f"/api/users/user_alice/skills/{draft['id']}/activate")
    client.post(f"/api/users/user_alice/skills/{draft['id']}/publish")
    published = next(item for item in client.get("/api/catalog/skills").json() if item["id"] == draft["id"])
    installed = client.post(f"/api/users/user_bob/catalog/{published['current_version_id']}/install").json()
    assert installed["user_id"] == "user_bob"
    assert installed["instructions"] == body["instructions"]
    assert installed["current_version_id"] != published["current_version_id"]
