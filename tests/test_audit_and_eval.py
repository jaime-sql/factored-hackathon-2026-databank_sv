from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.eval_access import DEMO_SAMPLE_LABEL
from app.i18n import ui_copy
from app.ops.guard import AuditImmutable
from tests.conftest import login

ROOT = Path(__file__).resolve().parents[1]


def test_case_id_is_server_uuid_and_eval_fields_need_the_token(client: TestClient) -> None:
    headers = login(client, "maria")
    refused = client.post(
        "/cases",
        headers=headers,
        json={
            "transaction_key": "tx_maria_pending",
            "message": "No reconozco este cargo",
            "case_id": "client-picked",
            "eval_run_id": "run-should-drop",
            "case_source": "sample",
        },
    )
    assert refused.status_code == 200, refused.text
    body = refused.json()
    assert body["case_id"] != "client-picked"
    uuid.UUID(body["case_id"])
    assert body["eval_run_id"] is None
    assert body["case_source"] is None
    stored = client.get(f"/cases/{body['case_id']}", headers=headers).json()
    assert stored["is_eval_case"] in (False, 0)
    assert stored["eval_run_id"] is None

    wrong = client.post(
        "/cases",
        headers={**headers, "EVAL_RUNNER_TOKEN": "nope"},
        json={
            "transaction_key": "tx_maria_reversed",
            "message": "No reconozco este cargo",
            "eval_run_id": "run-x",
            "case_source": "red_team",
        },
    )
    assert wrong.json()["eval_run_id"] is None
    assert wrong.json()["case_source"] is None

    bad_source = client.post(
        "/cases",
        headers={**headers, "EVAL_RUNNER_TOKEN": "runner-secret"},
        json={
            "transaction_key": "tx_maria_home",
            "message": "No reconozco este cargo",
            "eval_run_id": "run-1",
            "case_source": "production",
        },
    )
    assert bad_source.status_code == 422

    accepted = client.post(
        "/cases",
        headers={**headers, "EVAL_RUNNER_TOKEN": "runner-secret"},
        json={
            "transaction_key": "tx_maria_pending_30",
            "message": "No reconozco este cargo",
            "eval_run_id": "run-1",
            "case_source": "sample",
        },
    )
    assert accepted.status_code == 200, accepted.text
    saved = accepted.json()
    assert saved["eval_run_id"] == "run-1"
    assert saved["case_source"] == "sample"
    current = [
        row
        for row in client.app.state.ops.current_audit_cases()
        if row["case_id"] == saved["case_id"]
    ]
    assert len(current) == 1
    assert current[0]["eval_run_id"] == "run-1"
    assert current[0]["case_source"] == "sample"
    assert current[0]["is_eval_case"] is True


def test_metrics_exclude_eval_until_the_demo_sample_toggle(client: TestClient) -> None:
    headers = login(client, "maria")
    client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_pending", "message": "No reconozco este cargo"},
    )
    client.post(
        "/cases",
        headers={**headers, "EVAL_RUNNER_TOKEN": "runner-secret"},
        json={
            "transaction_key": "tx_maria_reversed",
            "message": "No reconozco este cargo",
            "eval_run_id": "run-demo",
            "case_source": "sample",
        },
    )
    quiet = client.get("/api/metrics").json()
    assert quiet["include_eval"] is False
    assert quiet["eval_toggle_label"] == DEMO_SAMPLE_LABEL
    assert quiet["k1_volume"]["total"] == 1
    assert quiet["excluded_eval_cases"] == 1
    included = client.get("/api/metrics?include_eval=true").json()
    assert included["k1_volume"]["total"] == 2
    assert included["excluded_eval_cases"] == 0
    page = client.get("/metrics")
    assert page.status_code == 200
    assert ui_copy("es")["eval_toggle"] in page.text
    assert DEMO_SAMPLE_LABEL not in page.text


def test_audit_rows_are_append_only(client: TestClient) -> None:
    headers = login(client, "maria")
    opened = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_pending", "message": "No reconozco este cargo"},
    ).json()
    before = client.app.state.ops.audit_case_count(opened["case_id"])
    with pytest_raises():
        client.app.state.ops.execute(
            "UPDATE audit_case SET decision = 'handoff' WHERE case_id = ?",
            (opened["case_id"],),
        )
    assert client.app.state.ops.audit_case_count(opened["case_id"]) == before
    contested = client.post(
        f"/cases/{opened['case_id']}/actions",
        headers=headers,
        json={"action": "contest"},
    )
    assert contested.status_code == 200, contested.text
    assert client.app.state.ops.audit_case_count(opened["case_id"]) == before + 1
    current = [
        row
        for row in client.app.state.ops.current_audit_cases()
        if row["case_id"] == opened["case_id"]
    ]
    assert current[0]["decision"] == "handoff"
    assert current[0]["handoff_reason"] == "customer_contests_rule_answer"
    assert current[0]["supersedes_audit_id"]


def pytest_raises() -> object:
    import pytest

    return pytest.raises(AuditImmutable)


def test_app_source_never_updates_an_audit_table() -> None:
    banned = (
        "update audit_case",
        "update app.audit_case",
        "update audit_llm_call",
        "update audit_event",
    )
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for phrase in banned:
            assert phrase not in text, path


def test_migration_grants_audit_current_to_eval_rw_if_the_role_exists() -> None:
    sql = (ROOT / "migrations" / "001_app_schema.sql").read_text(encoding="utf-8")
    grant = "GRANT SELECT ON app.audit_current TO eval_rw"
    assert grant in sql
    before = sql[: sql.index(grant)]
    assert "DO $$" in before
    assert "pg_roles" in before
    assert "eval_rw" in before
    assert "REVOKE UPDATE, DELETE ON app.audit_case FROM app_rw" in sql
    assert "REVOKE UPDATE, DELETE ON app.audit_llm_call FROM app_rw" in sql
    assert "supersedes_audit_id" in sql
    assert "eval_run_id" in sql
    assert "case_source" in sql
    assert "statement_timeout = '15s'" in sql
    assert "app_rw" in sql


def test_app_code_does_not_read_eval_labels() -> None:
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "eval.transaction_labels" not in text
        assert "eval.case_labels" not in text or "cannot read" in text
