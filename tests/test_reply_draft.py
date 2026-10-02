"""Reply drafts stay in the audit trail and are not sent until the agent says so."""

from __future__ import annotations

import logging
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.guardrails.draft_check import grounded as app_grounded
from app.handoff.packet import HandoffPacket
from app.reply.draft import compose_draft, has_placeholder
from evals.draft_check import grounded
from tests.conftest import login

ADMIN = {"Authorization": "Bearer demo-agent-local"}


def test_harness_reexports_the_app_check() -> None:
    assert grounded is app_grounded


def test_grounded_rejects_amounts_dates_and_merchants_outside_the_packet() -> None:
    packet = {
        "amount": "US$ 1.645,60",
        "date": "3 jul 2025, 14:30",
        "merchant": "T•••••••",
    }
    ok = grounded(
        "Vimos el cargo de US$ 1.645,60 del 3 jul 2025 en T•••••••.",
        packet,
    )
    assert ok == {"ok": True, "unsupported_facts": []}
    bad = grounded(
        "Vimos US$ 9,99 del 4 ago 2025 en A••••.",
        packet,
    )
    assert bad["ok"] is False
    assert "US$ 9,99" in bad["unsupported_facts"]
    assert any("ago" in item for item in bad["unsupported_facts"])
    assert "A••••" in bad["unsupported_facts"]
    mxn = grounded("Vimos MXN99.00.", {"amount": "MXN99.00", "date": "", "merchant": ""})
    assert mxn["ok"] is True
    other = grounded("Vimos MXN50.00.", {"amount": "MXN99.00", "date": "", "merchant": ""})
    assert other["ok"] is False


def test_handoff_draft_is_grounded_and_unsent(client: TestClient) -> None:
    headers = login(client, "maria")
    opened = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_review", "message": "No reconozco este cargo"},
    ).json()
    assert opened["state"] == "handed_off"
    packet = client.get(f"/api/handoff/{opened['case_id']}", headers=ADMIN)
    assert packet.status_code == 200, packet.text
    view = packet.json()["view"]
    assert view["reply_draft"]
    assert view["reply_draft"].startswith("Hola, María.")
    assert "Harbor Desk" in view["reply_draft"]
    assert "[" not in view["reply_draft"] and "]" not in view["reply_draft"]
    stored_packet = client.app.state.ops.get_handoff(opened["case_id"])
    assert stored_packet["packet"]["customer_first_name"] == "María"
    assert "Borrador" not in view["reply_draft"]
    assert view["reply_grounded"] is True
    assert view["reply_unsupported"] == []
    assert view["reply_sent"] == ""
    stored = client.app.state.ops.get_case(opened["case_id"])
    assert stored["reply_draft"] == view["reply_draft"]
    assert stored["reply_sent"] in (None, "")
    rows = client.app.state.ops.execute(
        "SELECT decision, supersedes_audit_id, audit_id FROM audit_case WHERE case_id = ?",
        (opened["case_id"],),
    )
    by_decision = {row["decision"]: row for row in rows}
    assert "handoff" in by_decision
    assert "reply_draft" in by_decision
    draft = by_decision["reply_draft"]
    assert draft["supersedes_audit_id"] == draft["audit_id"]
    current = [
        row
        for row in client.app.state.ops.current_audit_cases()
        if row["case_id"] == opened["case_id"]
    ]
    assert len(current) == 1
    assert current[0]["decision"] == "handoff"
    checked = client.post(
        f"/api/handoff/{opened['case_id']}/draft-check",
        headers=ADMIN,
        json={"text": view["reply_draft"] + " US$ 9,99"},
    ).json()
    assert checked["ok"] is False
    sent = client.post(
        f"/api/handoff/{opened['case_id']}/reply",
        headers=ADMIN,
        json={"text": view["reply_draft"]},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "reply_sent"
    assert sent.json()["ok"] is True
    again = client.post(
        f"/api/handoff/{opened['case_id']}/reply",
        headers=ADMIN,
        json={"text": view["reply_draft"]},
    )
    assert again.status_code == 409, again.text
    assert again.json()["error"] == "reply_already_sent"
    after = client.app.state.ops.get_case(opened["case_id"])
    assert after["state"] == "handed_off"
    assert after["reply_sent"] == view["reply_draft"]
    decisions = {
        row["decision"]
        for row in client.app.state.ops.execute(
            "SELECT decision FROM audit_case WHERE case_id = ?",
            (opened["case_id"],),
        )
    }
    assert "reply_sent" in decisions
    tip = [
        row
        for row in client.app.state.ops.current_audit_cases()
        if row["case_id"] == opened["case_id"]
    ]
    assert tip[0]["decision"] == "handoff"


def test_missing_reply_columns_skip_the_draft_without_a_500(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    path = client.app.state.ops.path
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE cases DROP COLUMN reply_draft")
        conn.execute("ALTER TABLE cases DROP COLUMN reply_sent")
    headers = login(client, "maria")
    with caplog.at_level(logging.WARNING, logger="app.ops.store"):
        opened = client.post(
            "/cases",
            headers=headers,
            json={"transaction_key": "tx_maria_review", "message": "No reconozco este cargo"},
        )
    assert opened.status_code == 200, opened.text
    assert "reply draft was not stored" in caplog.text
    sent = client.post(
        f"/api/handoff/{opened.json()['case_id']}/reply",
        headers=ADMIN,
        json={"text": "Revisamos el cargo."},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "reply_sent"


def _draft_packet(*, language: str = "es", first_name: str = "") -> HandoffPacket:
    return HandoffPacket.model_validate(
        {
            "case_id": "case-draft",
            "customer_key": "ck_other",
            "customer_first_name": first_name,
            "language": language,
            "transaction": {
                "transaction_key": "tx-1",
                "product_key": "card",
                "merchant_name": "Tienda",
                "merchant_category": "Food",
                "transaction_city": "Ciudad de México",
                "transaction_country": "Mexico",
                "transaction_status": "Approved",
                "amount": 10,
                "currency": "MXN",
                "transaction_ts_utc": "2026-01-15T18:00:00+00:00",
                "customer_tz": "America/Mexico_City",
                "transaction_ts_customer_local": "15 ene 2026, 12:00",
                "local_time_abbreviation": "CST",
            },
            "verified_facts": ["merchant=Tienda"],
            "triage": {
                "band": "review",
                "fraud_score": 12,
                "model_risk_score": 0.01,
                "model_version": "lgbm:test",
            },
            "actions_taken": [],
            "recommended_next_step": "Una persona revisa el caso.",
        }
    )


def test_template_uses_the_bank_name_and_a_neutral_greeting_without_a_first_name() -> None:
    settings = Settings(bank_display_name="North Pier")
    draft = compose_draft(_draft_packet(), "Mexico", settings)
    assert draft.status == "template"
    assert draft.text.startswith("Hola.")
    assert not draft.text.startswith("Hola,")
    assert "North Pier" in draft.text
    assert "[" not in draft.text
    portuguese = compose_draft(_draft_packet(language="pt", first_name="Ana"), "Brazil", settings)
    assert portuguese.text.startswith("Olá, Ana.")
    assert "North Pier" in portuguese.text
    named = compose_draft(_draft_packet(first_name="María"), "Mexico", Settings())
    assert named.text.startswith("Hola, María.")
    assert "Harbor Desk" in named.text
    blank = compose_draft(_draft_packet(first_name="[María]"), "Mexico", Settings())
    assert blank.text.startswith("Hola.")
    assert "[" not in blank.text
    placeholder_bank = compose_draft(
        _draft_packet(first_name="Teo"),
        "Mexico",
        Settings(bank_display_name="[Nombre del Banco]"),
    )
    assert "Harbor Desk" in placeholder_bank.text
    assert "[" not in placeholder_bank.text


def test_placeholder_draft_falls_back_to_the_template(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    assert has_placeholder("Hola [Nombre del Banco].")
    assert has_placeholder("Vimos [el comercio].")
    assert has_placeholder("Hola, María. Harbor Desk vio el cargo.") is False

    def fake_complete(
        settings: Settings, provider: str, facts: dict[str, str]
    ) -> tuple[str, str, int, int, int]:
        del settings, provider, facts
        return ("Hola [Nombre del Banco], vimos el cargo.", "gpt-4o-mini", 4, 2, 2)

    monkeypatch.setattr("app.reply.draft._complete", fake_complete)
    settings = Settings(llm_provider="openai", openai_api_key="sk-test")
    with caplog.at_level(logging.WARNING, logger="app.reply.draft"):
        draft = compose_draft(_draft_packet(first_name="María"), "Mexico", settings)
    assert draft.status == "error"
    assert draft.used_model is True
    assert draft.text.startswith("Hola, María.")
    assert "Harbor Desk" in draft.text
    assert "[" not in draft.text
    assert "placeholder" in caplog.text

    def clean_complete(
        settings: Settings, provider: str, facts: dict[str, str]
    ) -> tuple[str, str, int, int, int]:
        del settings, provider, facts
        return ("Hola, María. Harbor Desk vio el cargo.", "gpt-4o-mini", 4, 2, 2)

    monkeypatch.setattr("app.reply.draft._complete", clean_complete)
    kept = compose_draft(_draft_packet(first_name="María"), "Mexico", settings)
    assert kept.status == "ok"
    assert kept.text == "Hola, María. Harbor Desk vio el cargo."
