"""Pin the demo-persona routes. HIGH, pending, reversed, LightGBM, and duplicates."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import login

EXPECTED = {
    "tx_ana_home": ("review", "handed_off", "triage"),
    "tx_camilo_home": ("review", "handed_off", "triage"),
    "tx_camilo_abroad": ("low", "merchant_explained", "triage"),
    "tx_maria_dup_b": ("review", "handed_off", "duplicate_synthetic"),
    "tx_maria_home": ("review", "handed_off", "triage"),
    "tx_maria_pending": ("out_of_scope", "rule_explained", "pending"),
    "tx_maria_pending_30": ("out_of_scope", "rule_explained", "pending"),
    "tx_maria_pending_high": ("high", "awaiting_block_confirmation", "triage"),
    "tx_maria_reversed": ("out_of_scope", "rule_explained", "reversed"),
    "tx_maria_reversed_high": ("high", "awaiting_block_confirmation", "triage"),
    "tx_maria_low": ("review", "handed_off", "triage"),
    "tx_maria_review": ("review", "handed_off", "triage"),
    "tx_maria_nofeat": ("review", "handed_off", "triage"),
    "tx_maria_dup_a": ("review", "handed_off", "duplicate_synthetic"),
    "tx_teo_home": ("review", "handed_off", "triage"),
    "tx_teo_pending_high": ("high", "awaiting_block_confirmation", "triage"),
    "SYN_0112_B": ("low", "duplicate_explained", "duplicate_synthetic"),
    "tx_lucia_source": ("low", "merchant_explained", "triage"),
    "SYN_0112_A": ("low", "duplicate_explained", "duplicate_synthetic"),
}


def test_demo_persona_routes_stay_put(tmp_path: Path) -> None:
    settings = Settings(
        environment="local",
        bank_db_path=str(tmp_path / "bank.sqlite"),
        ops_db_path=str(tmp_path / "ops.sqlite"),
        database_url="",
        eval_runner_token="runner-secret",
        session_secret="test-session-secret-value",
        demo_agent_token="demo-agent-local",
        qa_test_token="",
    )
    app = create_app(settings)
    seen: dict[str, tuple[str, str, str]] = {}
    with TestClient(app) as client:
        personas = client.get("/api/personas").json()["personas"]
        assert [row["id"] for row in personas] == ["ana", "camilo", "maria", "teo", "lucia"]
        for persona in personas:
            headers = login(client, persona["id"])
            charges = client.get("/api/transactions?language=es", headers=headers).json()
            for tx in charges["transactions"]:
                opened = client.post(
                    "/cases",
                    headers=headers,
                    json={
                        "transaction_key": tx["transaction_key"],
                        "message": "No reconozco este cargo",
                        "language": "es",
                    },
                )
                assert opened.status_code == 200, opened.text
                body = opened.json()
                seen[tx["transaction_key"]] = (body["band"], body["state"], body["case_type"])
    assert seen == EXPECTED
