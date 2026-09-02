import asyncio

from fastapi.testclient import TestClient

from meta_workers.tools import REPORT_DISCLAIMER, ToolContext, publish_report_tool, validate_public_url
from test_chat import FinalModel, wait_for


def test_public_company_report_is_validated_and_published(client: TestClient):
    client.app.state.runner.model = FinalModel()
    run_id = client.post(
        "/api/users/user_alice/agents/agent_alice_kyc/runs",
        json={"prompt": "Research Acme.", "client_nonce": "nonce-report"},
    ).json()["id"]
    wait_for(lambda: client.get("/api/users/user_alice/agents/agent_alice_kyc/thread").json()["active_run"] is None)
    context = ToolContext(client.app.state.settings, client.app.state.db, client.app.state.sandbox, "user_alice", "agent_alice_kyc", run_id, "thread_alice_kyc")
    result = asyncio.run(publish_report_tool(context, {
        "company_name": "Acme PLC",
        "summary": "A public-source demonstration company.",
        "unknowns": ["Beneficial ownership was not established."],
        "next_manual_checks": ["Verify the company registry entry."],
        "sources": [{"claim": "Company homepage", "url": "https://example.com", "accessed_at": "2026-09-02"}],
    }))
    markdown = client.get(f"/api/users/user_alice/artifacts/{result['artifacts'][1]['id']}")
    report_json = client.get(f"/api/users/user_alice/artifacts/{result['artifacts'][0]['id']}").json()
    assert REPORT_DISCLAIMER in markdown.text
    assert report_json["disclaimer"] == REPORT_DISCLAIMER
    assert report_json["unknowns"]
    assert len(result["artifacts"]) == 2


def test_browser_rejects_loopback():
    try:
        asyncio.run(validate_public_url("http://127.0.0.1/private"))
    except ValueError as error:
        assert "private or reserved" in str(error)
    else:
        raise AssertionError("loopback URL was accepted")


def test_routine_validates_and_stores_schedule(client: TestClient):
    response = client.post("/api/users/user_alice/agents/agent_alice_kyc/routines", json={
        "name": "Weekly refresh", "prompt": "Refresh Acme research.", "cron": "0 9 * * 1", "timezone": "UTC",
    })
    assert response.status_code == 201
    assert response.json()["next_run_at"]
