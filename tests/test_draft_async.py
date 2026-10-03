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
