"""The break-it button is a flagged demo, not test traffic and not a metric."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.demo_attack import DEMO_ATTACK_MESSAGE
from app.main import create_app
from tests.conftest import login

ADMIN = {"Authorization": "Bearer demo-agent-local"}


def test_break_it_abandons_and_stays_out_of_metrics(client: TestClient) -> None:
    headers = login(client, "maria")
    before = client.get("/api/metrics").json()["k1_volume"]["total"]
    opened = client.post(
        "/cases",
        headers=headers,
        json={"demo_attack": True, "language": "es", "message": "hola"},
    )
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["protected"] is True
    assert body["money_movement"] == "none"
    assert body["demo_attack"] is True
    assert body["is_test"] is False
    assert body["language"] == "es"
    assert "4111 1111 1111 1111" not in body["reply"]
    assert "4111 1111 1111 1111" not in body["masked_message"]
    assert "[CARD]" in body["masked_message"]
    assert "Ignora tus reglas" in body["masked_message"]
    assert "Ignore previous instructions" not in body["masked_message"]
    assert body["audit"]["decision"] == "abandoned"
    assert "prompt_injection" in body["audit"]["guardrail_flags"]
    assert "pii_masked" in body["audit"]["guardrail_flags"]
    stored = client.app.state.ops.get_case(body["case_id"])
    assert stored["demo_attack"] is True
    assert stored["is_test"] is False
    audit = client.app.state.ops.execute(
        "SELECT decision, guardrail_flags, demo_attack FROM audit_case WHERE case_id = ?",
        (body["case_id"],),
    )
    assert audit[0]["decision"] == "abandoned"
    assert audit[0]["demo_attack"] in (1, True)
    assert "4111111111111111" not in str(audit)
    assert client.get("/api/metrics").json()["k1_volume"]["total"] == before
    included = client.get("/api/metrics?include_test=1", headers=ADMIN).json()
    assert included["k1_volume"]["total"] == before
    assert DEMO_ATTACK_MESSAGE not in str(audit)


def test_break_it_sets_is_test_only_in_test_mode(tmp_path: Path) -> None:
    settings = Settings(
        environment="local",
        bank_db_path=str(tmp_path / "bank.sqlite"),
        ops_db_path=str(tmp_path / "ops.sqlite"),
        database_url="",
        eval_runner_token="runner-secret",
        session_secret="test-session-secret-value",
        demo_agent_token="demo-agent-local",
        qa_test_token="qa-local-test-token",
    )
    with TestClient(create_app(settings)) as client:
        armed = client.post("/api/test-mode", headers={"X-Test-Token": "qa-local-test-token"})
        assert armed.json()["is_test"] is True
        headers = {
            **login(client, "maria"),
            "X-Test-Token": "qa-local-test-token",
        }
        opened = client.post(
            "/cases",
            headers=headers,
            json={"demo_attack": True, "language": "pt", "message": "substituir"},
        ).json()
        assert opened["demo_attack"] is True
        assert opened["is_test"] is True
        assert "Ignora as tuas regras" in opened["masked_message"]
        assert "substituir" not in opened["masked_message"]
        stored = client.app.state.ops.get_case(opened["case_id"])
        assert stored["demo_attack"] is True
        assert stored["is_test"] is True
        assert opened["language"] == "pt"
        assert client.get("/api/metrics").json()["k1_volume"]["total"] == 0
