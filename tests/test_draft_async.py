"""Reply drafts are written after the customer response, never on its path."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.api.routes as routes
import app.reply.draft as draft_module
from tests.conftest import login

ADMIN = {"Authorization": "Bearer demo-agent-local"}
SLOW_SECONDS = 2.0


@pytest.fixture
def slow_draft(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    calls = {"n": 0}
    real = draft_module.compose_draft

    def slow(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        time.sleep(SLOW_SECONDS)
        return real(*args, **kwargs)

    monkeypatch.setattr(draft_module, "compose_draft", slow)
    return calls


def _hold_drafts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    held: list[str] = []

    def hold(background: Any, engine: Any, case_ids: list[str]) -> None:
        del background, engine
        held.extend(case_ids)

    monkeypatch.setattr(routes, "_schedule_drafts", hold)
    return held


def test_review_decision_does_not_wait_on_the_draft_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, slow_draft: dict[str, int]
) -> None:
    held = _hold_drafts(monkeypatch)
    headers = login(client, "maria")
    started = time.monotonic()
    opened = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_review", "message": "No reconozco este cargo"},
    )
    elapsed = time.monotonic() - started
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["state"] == "handed_off"
    assert elapsed < SLOW_SECONDS, elapsed
    assert slow_draft["n"] == 0
    assert held == [body["case_id"]]
    stored = client.app.state.ops.get_case(body["case_id"])
    assert not stored.get("reply_draft")


def test_packet_shows_pending_then_the_draft_after_the_first_open(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, slow_draft: dict[str, int]
) -> None:
    _hold_drafts(monkeypatch)
    headers = login(client, "maria")
    case_id = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_review", "message": "No reconozco este cargo"},
    ).json()["case_id"]
    first = client.get(f"/api/handoff/{case_id}", headers=ADMIN).json()["view"]
    assert first["reply_draft"] == ""
    assert first["reply_draft_status"] == "pending"
    # TestClient runs the lazy background write before returning.
    assert slow_draft["n"] == 1
    second = client.get(f"/api/handoff/{case_id}", headers=ADMIN).json()["view"]
    assert second["reply_draft_status"] == "ready"
    assert second["reply_draft"].startswith("Hola, María.")
    assert second["reply_grounded"] is True
    assert slow_draft["n"] == 1
    rows = client.app.state.ops.execute(
        "SELECT decision FROM audit_case WHERE case_id = ? AND decision = 'reply_draft'",
        (case_id,),
    )
    assert len(rows) == 1


def test_background_draft_runs_after_the_customer_response(
    client: TestClient, slow_draft: dict[str, int]
) -> None:
    headers = login(client, "maria")
    case_id = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_review", "message": "No reconozco este cargo"},
    ).json()["case_id"]
    assert slow_draft["n"] == 1
    view = client.get(f"/api/handoff/{case_id}", headers=ADMIN).json()["view"]
    assert view["reply_draft_status"] == "ready"
    assert slow_draft["n"] == 1


def test_concurrent_draft_requests_compose_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, slow_draft: dict[str, int]
) -> None:
    _hold_drafts(monkeypatch)
    headers = login(client, "maria")
    case_id = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_review", "message": "No reconozco este cargo"},
    ).json()["case_id"]
    engine = client.app.state.engine
    results: list[bool] = []
    threads = [
        threading.Thread(target=lambda: results.append(engine.ensure_reply_draft(case_id)))
        for _ in range(3)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert slow_draft["n"] == 1
    assert results.count(True) == 1
    assert engine.ensure_reply_draft(case_id) is False
    assert slow_draft["n"] == 1


def _audit_count(client: TestClient, case_id: str) -> int:
    ops = client.app.state.ops
    total = 0
    for table in ("audit_case", "audit_llm_call"):
        rows = ops.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE case_id = ?", (case_id,))
        total += int(rows[0]["n"])
    return total


def _handoff(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    _hold_drafts(monkeypatch)
    headers = login(client, "maria")
    return client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_review", "message": "No reconozco este cargo"},
    ).json()["case_id"]


def test_draft_status_poll_writes_no_audit_rows(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, slow_draft: dict[str, int]
) -> None:
    case_id = _handoff(client, monkeypatch)
    before = _audit_count(client, case_id)
    for _ in range(5):
        polled = client.get(f"/api/handoff/{case_id}/draft", headers=ADMIN)
        assert polled.status_code == 200, polled.text
        assert polled.json() == {"case_id": case_id, "status": "pending"}
    assert _audit_count(client, case_id) == before
    assert slow_draft["n"] == 0, "polling never starts a draft"
    assert client.app.state.engine.ensure_reply_draft(case_id) is True
    after_draft = _audit_count(client, case_id)
    for _ in range(5):
        body = client.get(f"/api/handoff/{case_id}/draft", headers=ADMIN).json()
        assert body["status"] == "ready"
        assert body["reply_draft"].startswith("Hola, María.")
        assert set(body) == {
            "case_id",
            "status",
            "reply_draft",
            "reply_sent",
            "reply_grounded",
            "reply_unsupported",
        }
    assert _audit_count(client, case_id) == after_draft


def test_draft_status_needs_console_auth(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = _handoff(client, monkeypatch)
    assert client.get(f"/api/handoff/{case_id}/draft").status_code in {401, 403}
    assert client.post(f"/api/handoff/{case_id}/draft/retry").status_code in {401, 403}
    assert client.get("/api/handoff/missing/draft", headers=ADMIN).status_code == 404


def test_retry_runs_at_most_one_regeneration(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, slow_draft: dict[str, int]
) -> None:
    case_id = _handoff(client, monkeypatch)
    engine = client.app.state.engine
    assert engine.claim_draft(case_id) is True  # a draft is already in flight
    busy = client.post(f"/api/handoff/{case_id}/draft/retry", headers=ADMIN)
    assert busy.status_code == 202
    assert busy.json()["status"] == "generating"
    assert busy.json()["started"] is False
    assert client.get(f"/api/handoff/{case_id}/draft", headers=ADMIN).json()["status"] == (
        "generating"
    )
    assert slow_draft["n"] == 0
    with engine._draft_lock:
        engine._drafting.discard(case_id)

    results: list[int] = []

    def retry() -> None:
        results.append(
            client.post(f"/api/handoff/{case_id}/draft/retry", headers=ADMIN).status_code
        )

    threads = [threading.Thread(target=retry) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert slow_draft["n"] == 1, "concurrent retries compose once"
    assert all(code in {200, 202} for code in results), results
    ready = client.post(f"/api/handoff/{case_id}/draft/retry", headers=ADMIN)
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert slow_draft["n"] == 1
    rows = client.app.state.ops.execute(
        "SELECT decision FROM audit_case WHERE case_id = ? AND decision = 'reply_draft'",
        (case_id,),
    )
    assert len(rows) == 1
