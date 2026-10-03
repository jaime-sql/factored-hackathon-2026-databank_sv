"""Judge console actions record source='judge'. Public chat stays unset."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.ops.console_action import CONSOLE_ACTIONS
from app.ops.store import _SQLITE_AUDIT_VIEWS
from app.triage_model import ScriptedTriage
from tests.conftest import login

JUDGE = "judge-demo-token"
ADMIN = {"Authorization": "Bearer demo-agent-local"}


def _client(tmp_path: Path) -> TestClient:
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
    app = create_app(settings)
    client = TestClient(app)
    client.__enter__()
    client.app.state.engine.triage = ScriptedTriage({"tx_maria_review": "review"})
    return client


def _rows(client: TestClient, case_id: str) -> list[dict[str, object]]:
    return client.app.state.ops.execute(
        "SELECT audit_id, decision, source FROM audit_case WHERE case_id = ?",
        (case_id,),
    )


def test_judge_console_actions_are_tagged_and_stay_in_audit_live(tmp_path: Path) -> None:
    client = _client(tmp_path)
    try:
        login(client, "maria")
        opened = client.post(
            "/cases",
            headers={"Authorization": f"Bearer {JUDGE}"},
            json={"transaction_key": "tx_maria_review", "message": "No reconozco este cargo"},
        )
        assert opened.status_code == 200, opened.text
        case_id = str(opened.json()["case_id"])
        assert opened.json()["state"] == "handed_off"
        public = _rows(client, case_id)
        assert public
        assert {row["decision"] for row in public} <= {None, "handoff", "reply_draft"}
        assert all(row["source"] is None for row in public)
        public_ids = {row["audit_id"] for row in public}

        before = client.get("/api/metrics").json()["k1_volume"]["total"]
        judge = {"Authorization": f"Bearer {JUDGE}"}
        for headers in (ADMIN, judge):
            listed = client.get("/api/handoff", headers=headers)
            assert listed.status_code == 200, listed.text
            detail = client.get(f"/api/handoff/{case_id}", headers=headers)
            assert detail.status_code == 200, detail.text
            assert detail.json()["view"]["band"]
            checked = client.post(
                f"/api/handoff/{case_id}/draft-check",
                headers=headers,
                json={"text": "Hola."},
            )
            assert checked.status_code == 200, checked.text
            resolved = client.post(
                f"/api/handoff/{case_id}/resolve",
                headers=headers,
                json={"note": "visto"},
            )
            assert resolved.status_code == 200, resolved.text
        assert client.get("/api/metrics").json()["k1_volume"]["total"] == before

        stored = _rows(client, case_id)
        pairs = {(row["decision"], row["source"]) for row in stored}
        assert "console_list" not in {row["decision"] for row in stored}
        for action in CONSOLE_ACTIONS:
            decision = f"console_{action}"
            assert (decision, None) in pairs
            assert (decision, "judge") in pairs
        assert all(row["source"] is None for row in stored if row["audit_id"] in public_ids)

        live = client.app.state.ops.execute(
            "SELECT decision, source FROM audit_live WHERE case_id = ?",
            (case_id,),
        )
        live_pairs = {(row["decision"], row["source"]) for row in live}
        assert "console_list" not in {row["decision"] for row in live}
        for action in CONSOLE_ACTIONS:
            assert (f"console_{action}", "judge") in live_pairs
        assert ("handoff", None) in live_pairs
        assert ("reply_draft", "judge") not in live_pairs

        tips = [
            row for row in client.app.state.ops.current_audit_cases() if row["case_id"] == case_id
        ]
        assert len(tips) == 1
        assert tips[0]["decision"] == "handoff"
        assert tips[0].get("source") is None

        with sqlite3.connect(client.app.state.ops.path) as conn:
            names = [row[1] for row in conn.execute("PRAGMA table_info(audit_live)")]
        assert names[-1] == "source"
    finally:
        client.__exit__(None, None, None)


def test_listing_a_queue_writes_no_audit_and_returns(client: TestClient, monkeypatch) -> None:
    writes: list[object] = []
    appended: list[object] = []
    monkeypatch.setattr(
        client.app.state.engine,
        "record_console_action",
        lambda *args, **kwargs: writes.append(args),
    )

    def append(row: dict[str, object]) -> str:
        appended.append(row)
        return str(row.get("audit_id"))

    monkeypatch.setattr(client.app.state.ops, "append_audit_case", append)
    packet = {
        "language": "es",
        "transaction": {"amount": 10, "currency": "MXN", "merchant_name": "Cafe"},
        "triage": {"band": "review"},
    }
    rows = [
        {"case_id": f"case-{index}", "status": "queued", "packet": packet} for index in range(59)
    ]
    monkeypatch.setattr(client.app.state.ops, "list_handoffs", lambda: rows)
    monkeypatch.setattr(client.app.state.ops, "current_audit_cases", lambda: [])
    started = time.perf_counter()
    listed = client.get("/api/handoff", headers=ADMIN)
    elapsed = time.perf_counter() - started
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["queue"]) == 59
    assert writes == []
    assert appended == []
    assert elapsed < 1


def test_console_rows_copy_is_test_from_the_case(tmp_path: Path) -> None:
    from app.triage_model import ScriptedTriage

    settings = Settings(
        environment="local",
        bank_db_path=str(tmp_path / "bank.sqlite"),
        ops_db_path=str(tmp_path / "ops.sqlite"),
        database_url="",
        eval_runner_token="runner-secret",
        session_secret="test-session-secret-value",
        demo_agent_token="demo-agent-local",
        demo_judge_token=JUDGE,
        qa_test_token="qa-local-test-token",
    )
    with TestClient(create_app(settings)) as client:
        client.app.state.engine.triage = ScriptedTriage(
            {"tx_maria_review": "review", "tx_maria_home": "review"}
        )
        plain = client.post(
            "/cases",
            headers=login(client, "maria"),
            json={"transaction_key": "tx_maria_home", "message": "No reconozco este cargo"},
        )
        assert plain.status_code == 200, plain.text
        armed = client.post("/api/test-mode", headers={"X-Test-Token": "qa-local-test-token"})
        assert armed.json()["is_test"] is True
        opened = client.post(
            "/cases",
            headers={**login(client, "maria"), "X-Test-Token": "qa-local-test-token"},
            json={"transaction_key": "tx_maria_review", "message": "No reconozco este cargo"},
        )
        assert opened.status_code == 200, opened.text
        assert opened.json()["is_test"] is True
        case_id = str(opened.json()["case_id"])
        judge = {"Authorization": f"Bearer {JUDGE}"}
        assert client.get(f"/api/handoff/{case_id}", headers=ADMIN).status_code == 200
        checked = client.post(
            f"/api/handoff/{case_id}/draft-check",
            headers=judge,
            json={"text": "Hola."},
        )
        assert checked.status_code == 200, checked.text
        sent = client.post(
            f"/api/handoff/{case_id}/reply",
            headers=judge,
            json={"text": "Hola."},
        )
        assert sent.status_code == 200, sent.text
        resolved = client.post(
            f"/api/handoff/{case_id}/resolve",
            headers=judge,
            json={"note": "visto"},
        )
        assert resolved.status_code == 200, resolved.text
        rows = client.app.state.ops.execute(
            "SELECT decision, is_test, source FROM audit_case WHERE case_id = ?",
            (case_id,),
        )
        by_decision = {str(row["decision"]): row for row in rows}
        for decision in ("console_open", "console_draft", "console_resolve", "reply_sent"):
            assert by_decision[decision]["is_test"] in (1, True), decision
        assert by_decision["console_open"]["source"] is None
        assert by_decision["console_draft"]["source"] == "judge"
        assert by_decision["reply_sent"]["source"] == "judge"
        plain_id = str(plain.json()["case_id"])
        assert client.get(f"/api/handoff/{plain_id}", headers=ADMIN).status_code == 200
        plain_rows = client.app.state.ops.execute(
            "SELECT decision, is_test FROM audit_case "
            "WHERE case_id = ? AND decision = 'console_open'",
            (plain_id,),
        )
        assert plain_rows
        assert plain_rows[0]["is_test"] in (0, False)


def test_open_succeeds_when_the_source_column_is_missing(client: TestClient) -> None:
    headers = login(client, "maria")
    opened = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_review", "message": "No reconozco este cargo"},
    )
    assert opened.status_code == 200, opened.text
    path = client.app.state.ops.path
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "DROP VIEW IF EXISTS audit_live;"
            "DROP VIEW IF EXISTS audit_current;"
            "DROP VIEW IF EXISTS audit_llm_call_current;"
        )
        conn.execute("ALTER TABLE audit_case DROP COLUMN source")
        conn.executescript(_SQLITE_AUDIT_VIEWS)
    detail = client.get(f"/api/handoff/{opened.json()['case_id']}", headers=ADMIN)
    assert detail.status_code == 200, detail.text
