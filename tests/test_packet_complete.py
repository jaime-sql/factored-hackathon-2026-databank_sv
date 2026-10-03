"""Open-time handoffs record packet completeness on the audit row metrics read."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.handoff.packet import HandoffPacket, packet_is_complete
from app.metrics.compute import compute_metrics
from tests.conftest import login


def _current(client: TestClient, case_id: str) -> dict[str, object]:
    rows = [row for row in client.app.state.ops.current_audit_cases() if row["case_id"] == case_id]
    assert len(rows) == 1
    return rows[0]


def test_blank_merchant_is_incomplete() -> None:
    packet = HandoffPacket.model_validate(
        {
            "case_id": "case-1",
            "customer_key": "ck_mx_maria",
            "language": "es",
            "transaction": {
                "transaction_key": "tx_maria_review",
                "product_key": "card_maria",
                "merchant_name": "",
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
            "verified_facts": ["merchant=Comercio no identificado"],
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
    assert packet_is_complete(packet) is False
    filled = packet.model_copy(
        update={"transaction": packet.transaction.model_copy(update={"merchant_name": "Farmacia"})}
    )
    assert packet_is_complete(filled) is True


def test_review_open_records_completeness_at_insert(client: TestClient) -> None:
    headers = login(client, "maria")
    opened = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_review", "message": "No reconozco este cargo"},
    ).json()
    assert opened["actions"] == []
    current = _current(client, opened["case_id"])
    assert current["decision"] == "handoff"
    stored = client.app.state.ops.get_handoff(opened["case_id"])["packet"]
    assert current["handoff_packet_complete"] is packet_is_complete(
        HandoffPacket.model_validate(stored)
    )
    assert current["handoff_packet_complete"] is True
    assert client.app.state.ops.audit_case_count(opened["case_id"]) == 1
    metrics = compute_metrics(
        client.app.state.ops.current_audit_cases(), [], [], {}, include_eval=False
    )
    assert metrics["k5_handoff"]["packet_complete"]["k"] == 1


def test_review_duplicate_open_records_completeness(client: TestClient) -> None:
    from app.triage_model import ScriptedTriage

    client.app.state.engine.triage = ScriptedTriage({"tx_maria_dup_b": "review"})
    headers = login(client, "maria")
    opened = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_dup_b", "message": "No reconozco este cargo"},
    ).json()
    assert opened["case_type"] == "duplicate_synthetic"
    assert opened["actions"] == []
    current = _current(client, opened["case_id"])
    assert current["decision"] == "handoff"
    stored = client.app.state.ops.get_handoff(opened["case_id"])["packet"]
    assert current["handoff_packet_complete"] is packet_is_complete(
        HandoffPacket.model_validate(stored)
    )
    assert current["handoff_packet_complete"] is True


def test_action_handoff_records_computed_completeness(client: TestClient) -> None:
    headers = login(client, "maria")
    opened = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_pending", "message": "No reconozco este cargo"},
    ).json()
    handed = client.post(
        f"/cases/{opened['case_id']}/actions",
        headers=headers,
        json={"action": "contest"},
    )
    assert handed.status_code == 200
    current = _current(client, opened["case_id"])
    assert current["decision"] == "handoff"
    stored = client.app.state.ops.get_handoff(opened["case_id"])["packet"]
    assert current["handoff_packet_complete"] is packet_is_complete(
        HandoffPacket.model_validate(stored)
    )
    assert current["handoff_packet_complete"] is True
