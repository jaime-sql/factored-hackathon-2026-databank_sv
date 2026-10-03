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
    anonymous = client.get("/api/metrics?include_eval=1").json()
    assert anonymous["include_eval"] is False
    assert anonymous["k1_volume"]["total"] == 1
    assert anonymous["excluded_eval_cases"] == 1
    included = client.get(
        "/api/metrics?include_eval=1",
        headers={"Authorization": "Bearer demo-agent-local"},
    ).json()
    assert included["include_eval"] is True
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
    with pytest_raises():
        client.app.state.ops.execute(
            "UPDATE test_cases SET reason = 'changed' WHERE case_id = ?",
            (opened["case_id"],),
        )
    with pytest_raises():
        client.app.state.ops.execute(
            "DELETE FROM audit_case WHERE case_id = ?",
            (opened["case_id"],),
        )
    with pytest_raises():
        client.app.state.ops.execute(
            "DELETE FROM test_cases WHERE case_id = ?",
            (opened["case_id"],),
        )
    contested = client.post(
        f"/cases/{opened['case_id']}/actions",
        headers=headers,
        json={"action": "contest"},
    )
    assert contested.status_code == 200, contested.text
    assert client.app.state.ops.audit_case_count(opened["case_id"]) == before + 2
    decisions = {
        row["decision"]
        for row in client.app.state.ops.execute(
            "SELECT decision FROM audit_case WHERE case_id = ?",
            (opened["case_id"],),
        )
    }
    assert "reply_draft" in decisions
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
    view_sql = sql[
        sql.index("CREATE OR REPLACE VIEW app.audit_current") : sql.index(
            "CREATE OR REPLACE VIEW app.audit_llm_call_current"
        )
    ]
    assert "is_test" not in view_sql
    assert "test_cases" not in view_sql
    assert "eval_run_id" not in view_sql
    assert "GRANT SELECT, INSERT ON app.test_cases TO app_rw" in sql
    assert "REVOKE UPDATE, DELETE ON app.test_cases FROM app_rw" in sql
    assert "GRANT SELECT ON app.audit_live TO app_rw" in sql
    assert "GRANT SELECT ON app.audit_live TO eval_rw" in sql
    assert "GRANT SELECT ON app.test_cases TO eval_rw" in sql
    assert "GRANT UPDATE" not in sql
    assert "GRANT DELETE" not in sql
    sql002 = (ROOT / "migrations" / "002_is_test.sql").read_text(encoding="utf-8")
    assert "CREATE OR REPLACE VIEW app.audit_current" not in sql002
    assert "CREATE OR REPLACE VIEW app.audit_live" in sql002
    for phrase in (
        "ON app.audit_case TO",
        "ON app.audit_llm_call TO",
        "ON app.audit_event TO",
        "ON app.audit_current TO",
        "ON app.audit_case FROM",
        "ON app.audit_llm_call FROM",
        "ON app.audit_event FROM",
    ):
        assert phrase not in sql002, phrase
    from app.ops.store import _sql_statements

    parts = _sql_statements(ROOT / "migrations" / "002_is_test.sql")
    do_blocks = [part for part in parts if "DO $$" in part]
    assert len(do_blocks) == 1
    assert "GRANT SELECT ON app.audit_live TO eval_rw" in do_blocks[0]
    assert "GRANT SELECT ON app.test_cases TO eval_rw" in do_blocks[0]
    assert "END $$" in do_blocks[0]


def test_migration_003_leaves_app_rw_select_only_on_the_audit_views() -> None:
    from app.ops.store import _privileges_are_select_only, _sql_statements

    sql003 = (ROOT / "migrations" / "003_view_grants.sql").read_text(encoding="utf-8")
    sql002 = (ROOT / "migrations" / "002_is_test.sql").read_text(encoding="utf-8")
    revoke = (
        "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON "
        "app.audit_current, app.audit_live, app.audit_llm_call_current FROM app_rw"
    )
    grant = (
        "GRANT SELECT ON app.audit_current, app.audit_live, app.audit_llm_call_current TO app_rw"
    )
    assert revoke in sql003
    assert grant in sql003
    assert "alter default privileges" not in sql003.lower()
    assert revoke not in sql002
    parts = _sql_statements(ROOT / "migrations" / "003_view_grants.sql")
    assert parts == [revoke, grant]
    applied = "\n".join(parts).lower()
    assert "eval_rw" not in applied
    assert "default" not in applied
    store = (ROOT / "app" / "ops" / "store.py").read_text(encoding="utf-8")
    assert "003_view_grants.sql" in store
    views = {"audit_current", "audit_live", "audit_llm_call_current"}
    assert _privileges_are_select_only({name: {"SELECT"} for name in views})
    assert not _privileges_are_select_only({name: {"SELECT", "INSERT"} for name in views})
    assert not _privileges_are_select_only({"audit_current": {"SELECT"}})


def test_migration_004_appends_demo_attack_and_leaves_audit_grants() -> None:
    sql = (ROOT / "migrations" / "004_demo_attack.sql").read_text(encoding="utf-8")
    assert sql.count("ADD COLUMN IF NOT EXISTS demo_attack boolean NOT NULL DEFAULT false") == 3
    assert "ADD COLUMN IF NOT EXISTS reply_draft text" in sql
    assert "ADD COLUMN IF NOT EXISTS reply_sent text" in sql
    assert "DROP VIEW" not in sql.upper()
    assert "CREATE OR REPLACE VIEW app.audit_current" not in sql
    assert "CREATE OR REPLACE VIEW app.audit_live" in sql
    view = sql[sql.index("CREATE OR REPLACE VIEW app.audit_live") : sql.index("REVOKE")]
    assert view.index("cur.*") < view.index("AS demo_attack")
    assert "GRANT SELECT ON app.audit_live TO app_rw" in sql
    for phrase in (
        "ON app.audit_case",
        "ON app.audit_llm_call",
        "ON app.audit_event",
        "ON app.audit_current",
    ):
        assert phrase not in sql, phrase
    assert "GRANT INSERT" not in sql
    assert "GRANT UPDATE" not in sql
    assert "GRANT DELETE" not in sql


def test_migration_005_makes_reference_tables_select_only() -> None:
    from app.ops.store import _sql_statements

    sql = (ROOT / "migrations" / "005_readonly_reference.sql").read_text(encoding="utf-8")
    revoke = (
        "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON "
        "app.llm_price, app.analytics_assumption FROM app_rw"
    )
    grant = "GRANT SELECT ON app.llm_price, app.analytics_assumption TO app_rw"
    assert revoke in sql
    assert grant in sql
    assert sql.index(revoke) < sql.index(grant)
    assert "alter default privileges" not in sql.lower()
    parts = _sql_statements(ROOT / "migrations" / "005_readonly_reference.sql")
    assert parts == [revoke, grant]
    applied = "\n".join(parts).lower()
    for other in (
        "eval_rw",
        "audit_",
        "app.cases",
        "app.handoff",
        "app.test_cases",
        "public.",
        "default",
        "policy",
    ):
        assert other not in applied, other
    store = (ROOT / "app" / "ops" / "store.py").read_text(encoding="utf-8")
    assert "005_readonly_reference.sql" not in store


def test_migration_006_appends_source_and_leaves_audit_grants() -> None:
    sql = (ROOT / "migrations" / "006_judge_source.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS source text DEFAULT NULL" in sql
    assert "NOT NULL" not in sql
    assert "DROP VIEW" not in sql.upper()
    assert "CREATE OR REPLACE VIEW app.audit_current" not in sql
    assert "CREATE OR REPLACE VIEW app.audit_live" in sql
    view = sql[sql.index("CREATE OR REPLACE VIEW app.audit_live") : sql.index("REVOKE")]
    assert view.index("cur.*") < view.index("AS demo_attack") < view.index("AS source")
    assert "judge" not in view.lower()
    assert "GRANT SELECT ON app.audit_live TO app_rw" in sql
    assert "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON app.audit_live FROM app_rw" in sql
    for phrase in (
        "ON app.audit_case",
        "ON app.audit_llm_call",
        "ON app.audit_event",
        "ON app.audit_current",
        "GRANT INSERT",
        "GRANT UPDATE",
        "GRANT DELETE",
    ):
        assert phrase not in sql, phrase
    store = (ROOT / "app" / "ops" / "store.py").read_text(encoding="utf-8")
    assert "006_judge_source.sql" not in store


def test_app_code_does_not_write_reference_tables() -> None:
    """Postgres app_rw only selects these tables.

    The local SQLite demo seeds them once inside OpsStore._init_sqlite.
    That path does not run against app.llm_price or app.analytics_assumption.
    """
    verbs = ("insert", "update", "delete", "truncate")
    tables = ("llm_price", "analytics_assumption")
    found: list[str] = []
    for root in (ROOT / "app", ROOT / "scripts", ROOT / "evals"):
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            for line in path.read_text(encoding="utf-8").splitlines():
                lowered = line.lower()
                if not any(table in lowered for table in tables):
                    continue
                if not any(verb in lowered for verb in verbs):
                    continue
                found.append(f"{relative}: {line.strip()}")
    assert found == [
        'app/ops/store.py: "INSERT OR IGNORE INTO llm_price VALUES (?, ?, ?, ?, ?)",',
        'app/ops/store.py: "INSERT OR IGNORE INTO analytics_assumption VALUES (?, ?, ?)",',
    ]
    store = (ROOT / "app" / "ops" / "store.py").read_text(encoding="utf-8")
    assert 'if backend == "sqlite":\n            self._init_sqlite()' in store
    assert store.count("self._init_sqlite()") == 1
    init = store.split("def _init_sqlite", 1)[1].split("\n    def ", 1)[0]
    assert "INSERT OR IGNORE INTO llm_price" in init
    assert "INSERT OR IGNORE INTO analytics_assumption" in init
    assert "app.llm_price" not in store
    assert "app.analytics_assumption" not in store
    for root in (ROOT / "app", ROOT / "scripts", ROOT / "evals"):
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "app.llm_price" not in text
            assert "app.analytics_assumption" not in text


def test_app_code_does_not_read_eval_labels() -> None:
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "eval.transaction_labels" not in text
        assert "eval.case_labels" not in text or "cannot read" in text
