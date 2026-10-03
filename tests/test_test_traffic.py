"""QA test-traffic flag: session, metrics, and the one-off backfill."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.session import accepts_qa_test_token, read_session, sign_customer
from app.config import Settings
from app.ids import new_case_id
from app.main import create_app
from app.ops.store import _SCHEMA_RETRY_SECONDS, OpsStore
from scripts.mark_demo_cases_test import mark_cases_test
from tests.conftest import login

ROOT = Path(__file__).resolve().parents[1]
QA_TOKEN = "qa-local-test-token"
ADMIN = {"Authorization": "Bearer demo-agent-local"}
JUDGE = {"Authorization": "Bearer judge-local-token"}


@pytest.fixture
def qa_client(tmp_path: Path) -> object:
    settings = Settings(
        environment="local",
        bank_db_path=str(tmp_path / "bank.sqlite"),
        ops_db_path=str(tmp_path / "ops.sqlite"),
        database_url="",
        eval_runner_token="runner-secret",
        session_secret="test-session-secret-value",
        demo_agent_token="demo-agent-local",
        demo_judge_token="judge-local-token",
        qa_test_token=QA_TOKEN,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _open(
    client: TestClient, headers: dict[str, str], key: str = "tx_maria_pending"
) -> dict[str, object]:
    response = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": key, "message": "No reconozco este cargo"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _stored(client: TestClient, headers: dict[str, str], case_id: str) -> dict[str, object]:
    response = client.get(f"/cases/{case_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_token_compare_is_exact_and_empty_disables() -> None:
    assert accepts_qa_test_token("", "anything") is False
    assert accepts_qa_test_token(QA_TOKEN, "") is False
    assert accepts_qa_test_token(QA_TOKEN, "nope") is False
    assert accepts_qa_test_token(QA_TOKEN, "x" * 80) is False
    assert accepts_qa_test_token(QA_TOKEN, QA_TOKEN) is True
    legacy = sign_customer("test-session-secret-value", "ck_mx_maria", 1)
    # A freshly signed cookie carries the flag. Rebuild a four-part legacy cookie.
    parts = legacy.split(".")
    assert len(parts) == 5
    body = f"{parts[1]}.{parts[2]}"
    digest = hmac.new(b"test-session-secret-value", body.encode(), hashlib.sha256).hexdigest()
    old = f"cust.{body}.{digest}"
    assert read_session("test-session-secret-value", old) == ("ck_mx_maria", False)
    flagged = sign_customer("test-session-secret-value", "ck_mx_maria", 1, is_test=True)
    assert read_session("test-session-secret-value", flagged) == ("ck_mx_maria", True)


def test_flag_set_unset_and_wrong_token(qa_client: TestClient, client: TestClient) -> None:
    headers = login(qa_client, "maria")
    plain = _open(qa_client, headers, "tx_maria_pending")
    assert _stored(qa_client, headers, str(plain["case_id"]))["is_test"] is False

    wrong = qa_client.post(
        "/api/test-mode",
        headers={"X-Test-Token": "not-the-token"},
    )
    assert wrong.status_code == 200
    assert wrong.json() == {"is_test": False, "accepted": False}
    assert "error" not in wrong.json()
    assert QA_TOKEN not in wrong.text
    assert "not-the-token" not in wrong.text
    assert qa_client.cookies.get("hd_test") is None
    still = _open(qa_client, headers, "tx_maria_reversed")
    assert _stored(qa_client, headers, str(still["case_id"]))["is_test"] is False

    armed = qa_client.post("/api/test-mode", headers={"X-Test-Token": QA_TOKEN})
    assert armed.status_code == 200
    assert armed.json() == {"is_test": True, "accepted": True}
    assert QA_TOKEN not in armed.text
    assert qa_client.cookies.get("hd_test")
    # Once armed, a wrong token still reads is_test (the cookie) but is not accepted.
    again = qa_client.post("/api/test-mode", headers={"X-Test-Token": "not-the-token"})
    assert again.json() == {"is_test": True, "accepted": False}
    session = qa_client.post("/api/session", json={"persona": "maria"})
    assert session.status_code == 200
    assert session.json()["is_test"] is True
    assert QA_TOKEN not in session.text
    signed = read_session("test-session-secret-value", session.json()["token"])
    assert signed is not None and signed[1] is True
    headers = {"Authorization": f"Bearer {session.json()['token']}"}
    flagged = _open(qa_client, headers, "tx_maria_home")
    stored = _stored(qa_client, headers, str(flagged["case_id"]))
    assert stored["is_test"] is True
    assert stored["is_eval_case"] in (False, 0)
    audit = [
        row
        for row in qa_client.app.state.ops.current_audit_cases()
        if row["case_id"] == flagged["case_id"]
    ]
    assert audit[0]["is_test"] is True

    disabled = login(client, "maria")
    leaked = client.post(
        "/cases",
        headers={**disabled, "X-Test-Token": QA_TOKEN},
        json={"transaction_key": "tx_maria_pending", "message": "No reconozco este cargo"},
    )
    assert leaked.status_code == 200
    assert _stored(client, disabled, leaked.json()["case_id"])["is_test"] is False


def test_header_persists_for_the_rest_of_the_session(qa_client: TestClient) -> None:
    headers = login(qa_client, "maria")
    first = qa_client.post(
        "/cases",
        headers={**headers, "X-Test-Token": QA_TOKEN},
        json={"transaction_key": "tx_maria_pending", "message": "No reconozco este cargo"},
    )
    assert first.status_code == 200, first.text
    assert QA_TOKEN not in first.text
    assert _stored(qa_client, headers, first.json()["case_id"])["is_test"] is True
    second = _open(qa_client, headers, "tx_maria_reversed")
    assert _stored(qa_client, headers, str(second["case_id"]))["is_test"] is True


def test_eval_run_never_sets_is_test(qa_client: TestClient) -> None:
    headers = login(qa_client, "maria")
    accepted = qa_client.post(
        "/cases",
        headers={**headers, "X-Test-Token": QA_TOKEN, "EVAL_RUNNER_TOKEN": "runner-secret"},
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
    stored = _stored(qa_client, headers, str(saved["case_id"]))
    assert stored["is_eval_case"] is True
    assert stored["is_test"] is False
    audit = [
        row
        for row in qa_client.app.state.ops.current_audit_cases()
        if row["case_id"] == saved["case_id"]
    ]
    assert audit[0]["is_eval_case"] is True
    assert audit[0]["is_test"] is False


def test_metrics_and_export_exclude_test_unless_admin(qa_client: TestClient) -> None:
    headers = login(qa_client, "maria")
    _open(qa_client, headers, "tx_maria_pending")
    qa_client.post(
        "/cases",
        headers={**headers, "X-Test-Token": QA_TOKEN},
        json={"transaction_key": "tx_maria_reversed", "message": "No reconozco este cargo"},
    )
    qa_client.post(
        "/cases",
        headers={**headers, "EVAL_RUNNER_TOKEN": "runner-secret"},
        json={
            "transaction_key": "tx_maria_home",
            "message": "No reconozco este cargo",
            "eval_run_id": "run-demo",
            "case_source": "sample",
        },
    )
    quiet = qa_client.get("/api/metrics").json()
    assert quiet["k1_volume"]["total"] == 1
    assert quiet["excluded_test_cases"] == 1
    assert quiet["excluded_eval_cases"] == 1
    assert quiet["include_test"] is False
    assert quiet["include_eval"] is False

    asked = qa_client.get("/api/metrics?include_test=1&include_eval=1").json()
    assert asked["k1_volume"]["total"] == 1
    assert asked["include_test"] is False
    assert asked["include_eval"] is False

    judge = qa_client.get("/api/metrics?include_test=1&include_eval=1", headers=JUDGE).json()
    assert judge["k1_volume"]["total"] == 1
    assert judge["include_test"] is False

    test_only = qa_client.get("/api/metrics?include_test=1", headers=ADMIN).json()
    assert test_only["include_test"] is True
    assert test_only["include_eval"] is False
    assert test_only["k1_volume"]["total"] == 2
    assert test_only["excluded_eval_cases"] == 1
    assert test_only["excluded_test_cases"] == 0

    both = qa_client.get("/api/metrics?include_test=1&include_eval=1", headers=ADMIN).json()
    assert both["k1_volume"]["total"] == 3
    assert both["excluded_test_cases"] == 0
    assert both["excluded_eval_cases"] == 0

    denied = qa_client.get("/audit/export")
    assert denied.status_code == 401
    judge_export = qa_client.get("/audit/export?include_test=1", headers=JUDGE)
    assert judge_export.status_code == 403

    quiet_csv = qa_client.get("/audit/export", headers=ADMIN)
    assert quiet_csv.status_code == 200
    assert "is_test" in quiet_csv.text.splitlines()[0]
    assert quiet_csv.text.count("\n") == 2
    included_csv = qa_client.get("/audit/export?include_test=1&include_eval=1", headers=ADMIN)
    assert included_csv.text.count("\n") == 4
    assert "True" in included_csv.text or "true" in included_csv.text


def _audit_current_without_is_test(path: str) -> None:
    """Recreate the tip view with the column list it had before is_test existed."""
    with sqlite3.connect(path) as conn:
        columns = [str(row[1]) for row in conn.execute("PRAGMA table_info(audit_case)")]
        selected = ", ".join(f'"{name}"' for name in columns if name != "is_test")
        conn.execute("DROP VIEW IF EXISTS audit_live")
        conn.execute("DROP VIEW IF EXISTS audit_current")
        conn.execute(
            f"""
            CREATE VIEW audit_current AS
            SELECT {selected}
            FROM audit_case AS a
            WHERE NOT EXISTS (
              SELECT 1 FROM audit_case AS newer
              WHERE newer.supersedes_audit_id = a.audit_id
            )
            """
        )
        conn.execute(
            """
            CREATE VIEW audit_live AS
            SELECT cur.*
            FROM audit_current AS cur
            WHERE cur.eval_run_id IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM audit_case AS src
                WHERE src.audit_id = cur.audit_id AND src.is_test = 1
              )
              AND NOT EXISTS (
                SELECT 1 FROM test_cases AS marked
                WHERE marked.case_id = cur.case_id
              )
            """
        )


def test_view_without_is_test_still_flags_queue_and_metrics(qa_client: TestClient) -> None:
    headers = login(qa_client, "maria")
    plain = _open(qa_client, headers, "tx_maria_home")
    marked = _open(qa_client, headers, "tx_maria_reversed")
    contested = qa_client.post(
        f"/cases/{marked['case_id']}/actions",
        headers=headers,
        json={"action": "contest"},
    )
    assert contested.status_code == 200, contested.text
    flagged = qa_client.post(
        "/cases",
        headers={**headers, "X-Test-Token": QA_TOKEN},
        json={"transaction_key": "tx_maria_pending", "message": "No reconozco este cargo"},
    ).json()
    contested = qa_client.post(
        f"/cases/{flagged['case_id']}/actions",
        headers=headers,
        json={"action": "contest"},
    )
    assert contested.status_code == 200, contested.text
    assert qa_client.app.state.ops.get_case(str(marked["case_id"]))["is_test"] is False
    assert qa_client.app.state.ops.get_case(str(flagged["case_id"]))["is_test"] is True
    qa_client.app.state.ops.insert_test_case(str(marked["case_id"]), "demo")
    _audit_current_without_is_test(qa_client.app.state.ops.path)
    with sqlite3.connect(qa_client.app.state.ops.path) as conn:
        view_columns = {row[1] for row in conn.execute("PRAGMA table_info(audit_current)")}
    assert "is_test" not in view_columns

    tips = {row["case_id"]: row for row in qa_client.app.state.ops.current_audit_cases()}
    assert tips[flagged["case_id"]]["is_test"] is True
    assert tips[marked["case_id"]]["is_test"] is True
    assert tips[plain["case_id"]]["is_test"] is False

    queue = qa_client.get("/api/handoff", headers=ADMIN).json()
    cards = {item["case_id"]: item for item in queue["queue"]}
    assert cards[flagged["case_id"]]["is_test"] is True
    assert cards[marked["case_id"]]["is_test"] is True
    flagged_packet = qa_client.get(f"/api/handoff/{flagged['case_id']}", headers=ADMIN).json()
    marked_packet = qa_client.get(f"/api/handoff/{marked['case_id']}", headers=ADMIN).json()
    assert flagged_packet["view"]["is_test"] is True
    assert marked_packet["view"]["is_test"] is True

    quiet = qa_client.get("/api/metrics?language=es").json()
    assert quiet["k1_volume"]["total"] == 1
    assert quiet["excluded_test_cases"] == 2
    eval_only = qa_client.get("/api/metrics?include_eval=1", headers=ADMIN).json()
    assert eval_only["include_eval"] is True
    assert eval_only["include_test"] is False
    assert eval_only["k1_volume"]["total"] == 1
    assert eval_only["excluded_test_cases"] == 2
    included = qa_client.get("/api/metrics?include_test=1", headers=ADMIN).json()
    assert included["k1_volume"]["total"] == 3
    assert included["excluded_test_cases"] == 0


def test_mark_script_runs_without_pythonpath() -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    module = subprocess.run(
        [sys.executable, "-m", "scripts.mark_demo_cases_test", "--help"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert module.returncode == 0, module.stderr
    script = subprocess.run(
        [sys.executable, "scripts/mark_demo_cases_test.py", "--help"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert script.returncode == 0, script.stderr
    source = (ROOT / "scripts" / "mark_demo_cases_test.py").read_text(encoding="utf-8")
    assert "python -m scripts.mark_demo_cases_test" in source


def test_agent_packet_shows_the_flag(qa_client: TestClient) -> None:
    headers = login(qa_client, "maria")
    opened = qa_client.post(
        "/cases",
        headers={**headers, "X-Test-Token": QA_TOKEN},
        json={"transaction_key": "tx_maria_pending", "message": "No reconozco este cargo"},
    ).json()
    contested = qa_client.post(
        f"/cases/{opened['case_id']}/actions",
        headers=headers,
        json={"action": "contest"},
    )
    assert contested.status_code == 200, contested.text
    queue = qa_client.get("/api/handoff", headers=ADMIN).json()
    card = next(item for item in queue["queue"] if item["case_id"] == opened["case_id"])
    assert card["is_test"] is True
    detail = qa_client.get(f"/api/handoff/{opened['case_id']}", headers=ADMIN).json()
    assert detail["view"]["is_test"] is True


def test_sqlite_migration_adds_is_test_to_an_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE cases (
              case_id TEXT PRIMARY KEY,
              customer_key TEXT NOT NULL,
              transaction_key TEXT,
              state TEXT NOT NULL,
              language TEXT NOT NULL,
              case_type TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              closed_at TEXT,
              latest_audit_id TEXT,
              is_eval_case INTEGER NOT NULL DEFAULT 0,
              eval_run_id TEXT,
              case_source TEXT
            )
            """
        )
    ops = OpsStore("sqlite", path=str(path))
    OpsStore("sqlite", path=str(path))
    with sqlite3.connect(path) as conn:
        for table in ("cases", "audit_case", "audit_llm_call"):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert "is_test" in columns, table
    now = datetime.now(UTC)
    case_id = new_case_id()
    ops.insert_case(
        {
            "case_id": case_id,
            "customer_key": "ck_mx_maria",
            "transaction_key": None,
            "state": "closed",
            "language": "es",
            "case_type": "other",
            "created_at": now,
            "updated_at": now,
            "closed_at": now,
            "latest_audit_id": None,
            "is_eval_case": False,
            "eval_run_id": None,
            "case_source": None,
            "is_test": False,
        }
    )
    assert ops.get_case(case_id)["is_test"] is False
    with sqlite3.connect(path) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        views = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'view'")
        }
    assert "test_cases" in tables
    assert "audit_current" in views
    assert "audit_live" in views
    sql = (ROOT / "migrations" / "002_is_test.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS is_test boolean NOT NULL DEFAULT false" in sql
    assert "CREATE TABLE IF NOT EXISTS app.test_cases" in sql
    assert "CREATE OR REPLACE VIEW app.audit_live" in sql
    assert "CREATE OR REPLACE VIEW app.audit_current" not in sql
    assert re.search(r"(?i)\bdelete\s+from\b", sql) is None


def test_backfill_marks_ids_or_a_cutoff_and_deletes_nothing(tmp_path: Path) -> None:
    ops = OpsStore("sqlite", path=str(tmp_path / "ops.sqlite"))
    older = datetime.now(UTC) - timedelta(days=2)
    newer = datetime.now(UTC)
    old_id = new_case_id()
    new_id = new_case_id()
    audit_old = new_case_id()
    audit_new = new_case_id()

    def seed(
        case_id: str,
        audit_id: str,
        created: datetime,
        eval_run_id: str | None = None,
    ) -> None:
        ops.insert_case(
            {
                "case_id": case_id,
                "customer_key": "ck_mx_maria",
                "transaction_key": None,
                "state": "closed",
                "language": "es",
                "case_type": "other",
                "created_at": created,
                "updated_at": created,
                "closed_at": created,
                "latest_audit_id": audit_id,
                "is_eval_case": eval_run_id is not None,
                "eval_run_id": eval_run_id,
                "case_source": "sample" if eval_run_id else None,
                "is_test": False,
            }
        )
        ops.append_audit_case(
            {
                "audit_id": audit_id,
                "case_id": case_id,
                "supersedes_audit_id": None,
                "recorded_at": created,
                "case_type": "other",
                "customer_segment": "Basic",
                "final_resolution_status": "closed",
                "case_created_at": created,
                "case_closed_at": created,
                "decision": "abandoned",
                "automation_attempted": False,
                "handoff_reason": None,
                "handoff_packet_complete": None,
                "language": "es",
                "country": "MX",
                "accent_group": None,
                "rule_or_model_version": "rule",
                "prompt_version": "prompt_v1",
                "fraud_score": None,
                "model_risk_score": None,
                "guardrail_flags": [],
                "is_eval_case": eval_run_id is not None,
                "eval_run_id": eval_run_id,
                "case_source": "sample" if eval_run_id else None,
                "is_test": False,
            }
        )

    seed(old_id, audit_old, older)
    seed(new_id, audit_new, newer)
    before_audit = ops.audit_case_count(old_id) + ops.audit_case_count(new_id)
    before_current = len(ops.current_audit_cases())
    marked = mark_cases_test(ops, case_ids=[old_id, "missing-id"], reason="demo")
    assert marked == [old_id]
    assert ops.get_case(old_id)["is_test"] is False
    assert ops.get_case(new_id)["is_test"] is False
    assert len(ops.current_audit_cases()) == before_current
    assert ops.audit_case_count(old_id) + ops.audit_case_count(new_id) == before_audit
    assert ops.test_case_ids() == {old_id}
    live_ids = {row["case_id"] for row in ops.live_audit_cases()}
    assert old_id not in live_ids
    assert new_id in live_ids
    tip = next(row for row in ops.current_audit_cases() if row["case_id"] == old_id)
    assert tip["is_test"] is True
    assert tip["supersedes_audit_id"] is None
    stored = ops.execute("SELECT is_test FROM audit_case WHERE case_id = ?", (old_id,))
    assert stored[0]["is_test"] in (0, False)
    again = mark_cases_test(ops, case_ids=[old_id])
    assert again == []
    assert ops.test_case_ids() == {old_id}
    assert len(ops.current_audit_cases()) == before_current
    plain_id = new_case_id()
    eval_id = new_case_id()
    seed(plain_id, new_case_id(), older)
    seed(eval_id, new_case_id(), older, eval_run_id="run-before")
    cutoff = newer - timedelta(hours=1)
    marked_before = mark_cases_test(ops, before=cutoff)
    assert marked_before == [plain_id]
    assert eval_id not in ops.test_case_ids()
    assert new_id not in marked_before
    repeated = mark_cases_test(ops, before=cutoff)
    assert repeated == []
    assert ops.audit_case_count(old_id) + ops.audit_case_count(new_id) == before_audit
    source = (ROOT / "scripts" / "mark_demo_cases_test.py").read_text(encoding="utf-8")
    store_source = (ROOT / "app" / "ops" / "store.py").read_text(encoding="utf-8")
    assert re.search(r"(?i)\bdelete\s+from\b", source) is None
    assert re.search(r"(?i)\bupdate\b", source) is None
    assert "insert_test_case" in source
    assert "ON CONFLICT (case_id) DO NOTHING" in store_source
    assert "mark_cases_test(" in source


def _seed_tip(
    ops: OpsStore,
    case_id: str,
    *,
    is_test: bool = False,
    eval_run_id: str | None = None,
) -> None:
    now = datetime.now(UTC)
    ops.insert_case(
        {
            "case_id": case_id,
            "customer_key": "ck_mx_maria",
            "transaction_key": None,
            "state": "closed",
            "language": "es",
            "case_type": "other",
            "created_at": now,
            "updated_at": now,
            "closed_at": now,
            "latest_audit_id": case_id,
            "is_eval_case": eval_run_id is not None,
            "eval_run_id": eval_run_id,
            "case_source": "sample" if eval_run_id else None,
            "is_test": is_test,
        }
    )
    ops.append_audit_case(
        {
            "audit_id": case_id,
            "case_id": case_id,
            "supersedes_audit_id": None,
            "recorded_at": now,
            "case_type": "other",
            "customer_segment": "Basic",
            "final_resolution_status": "closed",
            "case_created_at": now,
            "case_closed_at": now,
            "decision": "abandoned",
            "automation_attempted": False,
            "handoff_reason": None,
            "handoff_packet_complete": None,
            "language": "es",
            "country": "MX",
            "accent_group": None,
            "rule_or_model_version": "rule",
            "prompt_version": "prompt_v1",
            "fraud_score": None,
            "model_risk_score": None,
            "guardrail_flags": [],
            "is_eval_case": eval_run_id is not None,
            "eval_run_id": eval_run_id,
            "case_source": "sample" if eval_run_id else None,
            "is_test": is_test,
        }
    )


def test_audit_live_excludes_inserted_test_marked_ids_and_eval(tmp_path: Path) -> None:
    ops = OpsStore("sqlite", path=str(tmp_path / "ops.sqlite"))
    live_id = new_case_id()
    inserted_id = new_case_id()
    marked_id = new_case_id()
    eval_id = new_case_id()
    _seed_tip(ops, live_id)
    _seed_tip(ops, inserted_id, is_test=True)
    _seed_tip(ops, marked_id)
    _seed_tip(ops, eval_id, eval_run_id="run-live")
    before_current = len(ops.current_audit_cases())
    ops.insert_test_case(marked_id, "demo")
    assert len(ops.current_audit_cases()) == before_current == 4
    assert {row["case_id"] for row in ops.live_audit_cases()} == {live_id}


def test_metrics_drop_marked_ids_until_admin_includes_them(client: TestClient) -> None:
    headers = login(client, "maria")
    opened = _open(client, headers)
    case_id = str(opened["case_id"])
    before = len(client.app.state.ops.current_audit_cases())
    client.app.state.ops.insert_test_case(case_id, "demo")
    assert len(client.app.state.ops.current_audit_cases()) == before
    quiet = client.get("/api/metrics").json()
    assert quiet["k1_volume"]["total"] == 0
    assert quiet["excluded_test_cases"] == 1
    included = client.get("/api/metrics?include_test=1", headers=ADMIN).json()
    assert included["k1_volume"]["total"] == 1
    assert included["excluded_test_cases"] == 0
    export = client.get("/audit/export", headers=ADMIN)
    assert export.text.count("\n") == 1
    exported = client.get("/audit/export?include_test=1", headers=ADMIN)
    assert case_id in exported.text


def _strip_test_schema(path: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("DROP VIEW IF EXISTS audit_live")
        conn.execute("DROP VIEW IF EXISTS audit_current")
        conn.execute("DROP VIEW IF EXISTS audit_llm_call_current")
        for table in ("cases", "audit_case", "audit_llm_call"):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if "is_test" in columns:
                conn.execute(f"ALTER TABLE {table} DROP COLUMN is_test")
        conn.execute("DROP TABLE IF EXISTS test_cases")
        conn.execute(
            """
            CREATE VIEW audit_current AS
            SELECT * FROM audit_case AS a
            WHERE NOT EXISTS (
              SELECT 1 FROM audit_case AS newer
              WHERE newer.supersedes_audit_id = a.audit_id
            )
            """
        )
        conn.execute(
            """
            CREATE VIEW audit_llm_call_current AS
            SELECT * FROM audit_llm_call AS a
            WHERE NOT EXISTS (
              SELECT 1 FROM audit_llm_call AS newer
              WHERE newer.supersedes_audit_id = a.audit_id
            )
            """
        )


def test_missing_test_schema_keeps_serving(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    ops = client.app.state.ops
    _strip_test_schema(ops.path)
    with caplog.at_level(logging.WARNING, logger="app.ops.store"):
        assert ops.refresh_test_schema() is False
    assert "test-traffic schema is missing" in caplog.text
    assert "audit_current" in caplog.text
    health = client.get("/health").json()
    assert health["migrations_ok"] is False
    assert client.get("/healthz").json()["migrations_ok"] is False
    headers = login(client, "maria")
    opened = client.post(
        "/cases",
        headers={**headers, "X-Test-Token": "qa-local-test-token"},
        json={"transaction_key": "tx_maria_pending", "message": "No reconozco este cargo"},
    )
    assert opened.status_code == 200, opened.text
    with sqlite3.connect(ops.path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(cases)")}
        assert "is_test" not in columns
        assert conn.execute("SELECT count(*) FROM cases").fetchone()[0] == 1
    assert ops.test_case_ids() == set()
    metrics = client.get("/api/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["k1_volume"]["total"] == 1
    exported = client.get("/audit/export", headers=ADMIN)
    assert exported.status_code == 200
    assert opened.json()["case_id"] in exported.text


def test_missing_test_schema_refuses_a_test_mode_case(qa_client: TestClient) -> None:
    ops = qa_client.app.state.ops
    _strip_test_schema(ops.path)
    headers = login(qa_client, "maria")
    refused = qa_client.post(
        "/cases",
        headers={**headers, "X-Test-Token": QA_TOKEN},
        json={"message": "hola"},
    )
    assert refused.status_code == 503, refused.text
    body = refused.json()
    assert body["error"] == "test_schema_missing"
    assert "002_is_test" in body["message"]
    assert "not opened" in body["message"]
    with sqlite3.connect(ops.path) as conn:
        assert conn.execute("SELECT count(*) FROM cases").fetchone()[0] == 0
    again = qa_client.post(
        "/cases",
        headers={**headers, "X-Test-Token": QA_TOKEN},
        json={"message": "hola"},
    )
    assert again.status_code == 503, again.text
    opened = qa_client.post("/cases", headers=headers, json={"message": "hola"})
    assert opened.status_code == 200, opened.text
    assert opened.json()["is_test"] is False
    assert opened.json()["demo_attack"] is False
    with sqlite3.connect(ops.path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(cases)")}
        assert "is_test" not in columns
        assert conn.execute("SELECT count(*) FROM cases").fetchone()[0] == 1


def test_schema_probe_caches_true_and_retries_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ops = OpsStore("sqlite", path=str(tmp_path / "ops.sqlite"))
    assert ops.migrations_ok is True
    calls = {"n": 0}

    def probe() -> bool:
        calls["n"] += 1
        return calls["n"] >= 2

    ops._probe_test_schema = probe  # type: ignore[method-assign]
    clock = {"t": 5_000.0}
    monkeypatch.setattr("app.ops.store.time.monotonic", lambda: clock["t"])
    assert ops.refresh_test_schema() is False
    assert calls["n"] == 1
    assert ops.migrations_ok is False
    assert calls["n"] == 1
    clock["t"] += _SCHEMA_RETRY_SECONDS - 0.1
    assert ops.migrations_ok is False
    assert calls["n"] == 1
    clock["t"] += 0.1
    assert ops.migrations_ok is True
    assert calls["n"] == 2
    clock["t"] += 10_000
    ops._probe_test_schema = lambda: False  # type: ignore[method-assign]
    assert ops.migrations_ok is True
    assert calls["n"] == 2


def test_health_retries_a_false_schema_and_then_keeps_it(
    qa_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ops = qa_client.app.state.ops
    _strip_test_schema(ops.path)
    assert ops.refresh_test_schema() is False
    assert qa_client.get("/health").json()["migrations_ok"] is False
    clock = {"t": ops._schema_checked_at}
    monkeypatch.setattr("app.ops.store.time.monotonic", lambda: clock["t"])
    ops._probe_test_schema = lambda: True  # type: ignore[method-assign]
    assert qa_client.get("/health").json()["migrations_ok"] is False
    clock["t"] = ops._schema_checked_at + _SCHEMA_RETRY_SECONDS
    assert qa_client.get("/health").json()["migrations_ok"] is True
    assert qa_client.get("/healthz").json()["migrations_ok"] is True
    ops._probe_test_schema = lambda: False  # type: ignore[method-assign]
    clock["t"] += 120
    assert qa_client.get("/health").json()["migrations_ok"] is True


def test_post_cases_reports_is_test_and_demo_attack(
    client: TestClient, qa_client: TestClient
) -> None:
    plain = client.post("/cases", headers=login(client, "maria"), json={"message": "hola"})
    assert plain.status_code == 200, plain.text
    assert plain.json()["is_test"] is False
    assert plain.json()["demo_attack"] is False
    session = qa_client.post(
        "/api/session",
        json={"persona": "maria"},
        headers={"X-Test-Token": QA_TOKEN},
    )
    assert session.status_code == 200, session.text
    opened = qa_client.post(
        "/cases",
        headers={"Authorization": f"Bearer {session.json()['token']}"},
        json={"message": "hola"},
    )
    assert opened.status_code == 200, opened.text
    assert opened.json()["is_test"] is True
    assert opened.json()["demo_attack"] is False


def test_test_session_excludes_abandoned_from_live_metrics(qa_client: TestClient) -> None:
    ops = qa_client.app.state.ops
    before = len(ops.current_audit_cases())
    session = qa_client.post(
        "/api/session",
        json={"persona": "maria"},
        headers={"X-Test-Token": QA_TOKEN},
    )
    assert session.status_code == 200, session.text
    body = session.json()
    assert body["is_test"] is True
    assert QA_TOKEN not in session.text
    signed = read_session("test-session-secret-value", body["token"])
    assert signed is not None and signed[1] is True
    assert len(ops.current_audit_cases()) == before

    opened = qa_client.post(
        "/cases",
        headers={"Authorization": f"Bearer {body['token']}"},
        json={"message": "hola"},
    )
    assert opened.status_code == 200, opened.text
    case_id = opened.json()["case_id"]
    tips = [row for row in ops.current_audit_cases() if row["case_id"] == case_id]
    assert len(tips) == 1
    assert tips[0]["decision"] == "abandoned"
    assert tips[0]["is_test"] is True
    assert all(row["case_id"] != case_id for row in ops.live_audit_cases())
    quiet = qa_client.get("/api/metrics").json()
    assert quiet["k1_volume"]["total"] == 0
    assert quiet["excluded_test_cases"] == 1


def test_customer_page_sends_the_token_from_the_field_not_the_url() -> None:
    source = (ROOT / "static" / "js" / "desk.js").read_text(encoding="utf-8")
    assert 'get("test")' not in source
    assert "?test=" not in source
    completed = subprocess.run(
        ["node", "tests/test_test_mode.js"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
