"""The judge token is not an eval runner and cannot stamp or read eval traffic."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.triage_model import ScriptedTriage

ROOT = Path(__file__).resolve().parents[1]
JUDGE = "judge-demo-token"


def test_equal_judge_and_runner_tokens_refuse_to_start() -> None:
    with pytest.raises(ValueError, match="DEMO_JUDGE_TOKEN"):
        Settings(
            environment="local",
            demo_judge_token="same-secret-value",
            eval_runner_token="same-secret-value",
            session_secret="test-session-secret-value",
        )


def test_readme_points_at_the_submission_email_without_a_token() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Demo access" in readme
    assert "Demo token provided in the submission email" in readme
    assert "<DEMO_JUDGE_TOKEN>" in readme
    assert "judge-demo-token" not in readme
    assert "same-secret-value" not in readme


def test_judge_cannot_set_eval_run_or_open_eval_export(tmp_path: Path) -> None:
    settings = Settings(
        environment="local",
        bank_db_path=str(tmp_path / "bank.sqlite"),
        ops_db_path=str(tmp_path / "ops.sqlite"),
        database_url="",
        eval_runner_token="runner-secret",
        session_secret="test-session-secret-value",
        demo_agent_token="demo-agent-local",
        demo_judge_token=JUDGE,
    )
    with TestClient(create_app(settings)) as client:
        client.app.state.engine.triage = ScriptedTriage(
            {"tx_maria_low": "low", "tx_maria_home": "low"}
        )
        signed = client.post("/api/session", json={"persona": "maria"})
        assert signed.status_code == 200, signed.text
        session = signed.json()["token"]
        stamped = client.post(
            "/cases",
            headers={
                "Authorization": f"Bearer {session}",
                "EVAL_RUNNER_TOKEN": "runner-secret",
            },
            json={
                "transaction_key": "tx_maria_home",
                "message": "No reconozco este cargo",
                "eval_run_id": "run-real",
                "case_source": "sample",
            },
        )
        assert stamped.status_code == 200, stamped.text
        assert stamped.json()["eval_run_id"] == "run-real"

        blocked = client.post(
            "/cases",
            headers={
                "Authorization": f"Bearer {JUDGE}",
                "EVAL_RUNNER_TOKEN": "runner-secret",
            },
            json={
                "transaction_key": "tx_maria_low",
                "message": "No reconozco este cargo",
                "eval_run_id": "run-judge",
                "case_source": "sample",
            },
        )
        assert blocked.status_code == 200, blocked.text
        body = blocked.json()
        assert body["eval_run_id"] is None
        assert body["case_source"] is None
        stored = client.app.state.ops.get_case(body["case_id"])
        assert stored is not None
        assert stored["eval_run_id"] is None
        assert stored["case_source"] is None

        judge = {"Authorization": f"Bearer {JUDGE}"}
        assert client.get("/audit/export", headers=judge).status_code == 403
        plain = client.get("/api/metrics").json()["k1_volume"]["total"]
        forced = client.get("/api/metrics?include_eval=1", headers=judge)
        assert forced.status_code == 200, forced.text
        assert forced.json()["k1_volume"]["total"] == plain
        admin = client.get(
            "/api/metrics?include_eval=1",
            headers={"Authorization": "Bearer demo-agent-local"},
        )
        assert admin.status_code == 200, admin.text
        assert admin.json()["k1_volume"]["total"] > plain
