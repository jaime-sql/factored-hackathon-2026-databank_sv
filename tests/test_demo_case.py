"""Home demo-button cases are stored as test traffic and stay out of Métricas."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from tests.conftest import login

ROOT = Path(__file__).resolve().parents[1]
DEMO_KEYS = {"tx_maria_review", "tx_maria_pending", "tx_maria_reversed_high"}


def _counts(client: TestClient) -> tuple[int, int]:
    body = client.get("/api/metrics").json()
    return body["k1_volume"]["total"], len(client.app.state.ops.live_audit_cases())


def test_demo_button_case_does_not_change_metrics(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "DEMO_TRANSACTIONS", frozenset(DEMO_KEYS))
    headers = login(client, "maria")  # public mode: no test token anywhere
    real = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_low", "message": "No reconozco este cargo"},
    )
    assert real.status_code == 200, real.text
    before = _counts(client)
    assert before[0] == 1
    for key in sorted(DEMO_KEYS):
        demo = client.post(
            "/cases",
            headers=headers,
            json={"transaction_key": key, "message": "No reconozco este cargo", "demo_case": True},
        )
        assert demo.status_code == 200, demo.text
        assert demo.json()["is_test"] is True
        stored = client.get(f"/cases/{demo.json()['case_id']}", headers=headers).json()
        assert stored["is_test"] in (True, 1)
        for action in demo.json().get("actions", []):
            client.post(
                f"/cases/{demo.json()['case_id']}/actions",
                headers=headers,
                json={"action": action["id"]},
            )
    assert _counts(client) == before


def test_demo_flag_only_applies_to_the_demo_charges(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "DEMO_TRANSACTIONS", frozenset(DEMO_KEYS))
    headers = login(client, "maria")
    before = _counts(client)
    other = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_low", "message": "No reconozco", "demo_case": True},
    )
    assert other.status_code == 200, other.text
    assert other.json()["is_test"] is False
    assert _counts(client) == (before[0] + 1, before[1] + 1)


def test_demo_transactions_match_the_home_buttons() -> None:
    desk = (ROOT / "static/js/desk.js").read_text(encoding="utf-8")
    block = desk[desk.index("const DEMOS = [") : desk.index("];", desk.index("const DEMOS = ["))]
    assert set(re.findall(r'transaction: "([^"]+)"', block)) == set(routes.DEMO_TRANSACTIONS)
    assert "demo_case: true" in desk
