"""FORCE_TEST_CASES tag revisions, the live Consola queue filter, and containment."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.metrics.compute import compute_metrics
from tests.conftest import login

ADMIN = {"Authorization": "Bearer demo-agent-local"}
QA_TOKEN = "qa-local-test-token"


def _settings(tmp_path: Path, **extra: object) -> Settings:
    return Settings(
        environment="local",
        bank_db_path=str(tmp_path / "bank.sqlite"),
        ops_db_path=str(tmp_path / "ops.sqlite"),
        database_url="",
        session_secret="test-session-secret-value",
        demo_agent_token="demo-agent-local",
        qa_test_token=QA_TOKEN,
        **extra,
    )


@pytest.fixture
def tag_client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(tmp_path, force_test_cases=True))) as client:
        yield client


@pytest.fixture
def live_client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(tmp_path))) as client:
        yield client


def _review(client: TestClient, headers: dict[str, str]) -> str:
    body = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_review", "message": "No reconozco este cargo"},
    ).json()
    return str(body["case_id"])


def test_env_flag_parses_and_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORCE_TEST_CASES", raising=False)
    assert Settings().force_test_cases is False
    monkeypatch.setenv("FORCE_TEST_CASES", "true")
    assert Settings().force_test_cases is True


def test_forced_revision_stores_every_case_and_audit_row_as_test(tag_client: TestClient) -> None:
    assert tag_client.get("/health").json()["force_test"] is True
    headers = login(tag_client, "maria")  # no test token anywhere
    case_id = _review(tag_client, headers)
    clarify = tag_client.post("/cases", headers=headers, json={"message": "hola"}).json()
    ops = tag_client.app.state.ops
    for cid in (case_id, str(clarify["case_id"])):
        assert ops.execute("SELECT is_test FROM cases WHERE case_id = ?", (cid,))[0]["is_test"]
        rows = ops.execute("SELECT is_test FROM audit_case WHERE case_id = ?", (cid,))
        assert rows and all(row["is_test"] for row in rows)
    calls = ops.execute("SELECT is_test FROM audit_llm_call")
    assert all(row["is_test"] for row in calls)
    assert ops.live_audit_cases() == []
    assert tag_client.get("/api/metrics").json()["k1_volume"]["total"] == 0
    # The QA console on a tag still sees its own test cases.
    queue = tag_client.get("/api/handoff", headers=ADMIN).json()["queue"]
    assert case_id in {item["case_id"] for item in queue}


def test_live_revision_has_no_flag_and_counts_real_cases(live_client: TestClient) -> None:
    assert live_client.get("/health").json()["force_test"] is False
    case_id = _review(live_client, login(live_client, "maria"))
    stored = live_client.app.state.ops.execute(
        "SELECT is_test FROM cases WHERE case_id = ?", (case_id,)
    )
    assert not stored[0]["is_test"]
    assert live_client.get("/api/metrics").json()["k1_volume"]["total"] == 1


def test_live_queue_leaves_out_test_cases(live_client: TestClient) -> None:
    real = _review(live_client, login(live_client, "maria"))
    armed = live_client.post("/api/test-mode", headers={"X-Test-Token": QA_TOKEN})
    assert armed.json()["accepted"] is True
    tested = _review(live_client, login(live_client, "maria"))
    live_client.cookies.clear()
    queue = {
        item["case_id"] for item in live_client.get("/api/handoff", headers=ADMIN).json()["queue"]
    }
    assert real in queue
    assert tested not in queue, "is_test cases stay out of the live Consola queue"
    marked = _review(live_client, login(live_client, "maria"))
    assert live_client.app.state.ops.insert_test_case(marked, "qa") == 1
    queue = {
        item["case_id"] for item in live_client.get("/api/handoff", headers=ADMIN).json()["queue"]
    }
    assert marked not in queue, "app.test_cases members stay out too"
    # An armed QA session on live still sees test cases.
    live_client.post("/api/test-mode", headers={"X-Test-Token": QA_TOKEN})
    queue = {
        item["case_id"] for item in live_client.get("/api/handoff", headers=ADMIN).json()["queue"]
    }
    assert {real, tested, marked} <= queue


def _row(case_id: str, decision: str | None, status: str, case_type: str = "triage") -> dict:
    return {
        "case_id": case_id,
        "decision": decision,
        "final_resolution_status": status,
        "case_type": case_type,
        "automation_attempted": True,
        "handoff_reason": "x" if decision == "handoff" else None,
        "handoff_packet_complete": True,
        "case_created_at": None,
        "case_closed_at": None,
    }


def test_containment_leaves_clarifying_out_of_both_numbers() -> None:
    rows = [
        _row("a", "auto_resolved", "pending_explained"),
        _row("b", "auto_resolved", "merchant_recognized"),
        _row("c", "handoff", "handed_off"),
        _row("d", "abandoned", "injection_blocked"),
        _row("e", "abandoned", "clarifying", "other"),
        _row("f", "abandoned", "clarifying", "other"),
        _row("g", None, "awaiting_block_confirmation"),
    ]
    out = compute_metrics(rows, [], [], {}, include_eval=False, excluded_eval=0, excluded_test=0)
    # closed without handoff (a, b, d) / closed (a, b, c, d); e and f wait on the customer
    assert (out["k6_containment"]["k"], out["k6_containment"]["n"]) == (3, 4)
    assert (out["k5_handoff"]["k"], out["k5_handoff"]["n"]) == (1, 4)
    assert out["still_open"] == 3
