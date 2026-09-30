"""Queue cards and the expanded handoff view. No raw customer text."""

from __future__ import annotations

from typing import Any

from app.i18n import handoff_reason_label, mask_merchant, money, threshold_crossed


def _packet(row: dict[str, Any]) -> dict[str, Any]:
    packet = row.get("packet")
    return packet if isinstance(packet, dict) else {}


def _transaction(packet: dict[str, Any]) -> dict[str, Any]:
    transaction = packet.get("transaction")
    return transaction if isinstance(transaction, dict) else {}


def _triage(packet: dict[str, Any]) -> dict[str, Any]:
    triage = packet.get("triage")
    return triage if isinstance(triage, dict) else {}


def _actions(packet: dict[str, Any]) -> list[dict[str, Any]]:
    actions = packet.get("actions_taken") or []
    if not isinstance(actions, list):
        return []
    return [item for item in actions if isinstance(item, dict)]


def _card_blocked(packet: dict[str, Any]) -> bool:
    return any(
        item.get("name") == "block_card" and item.get("verification_status") == "verified"
        for item in _actions(packet)
    )


def _amount(transaction: dict[str, Any]) -> str:
    raw = transaction.get("amount")
    currency = str(transaction.get("currency") or "")
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return currency
    try:
        amount = float(raw)
    except ValueError:
        return currency
    if not currency:
        return f"{amount:,.2f}"
    return money(amount, currency)


def queue_card(row: dict[str, Any], audit: dict[str, Any] | None) -> dict[str, Any]:
    packet = _packet(row)
    transaction = _transaction(packet)
    triage = _triage(packet)
    audit_row = audit or {}
    language = str(packet.get("language") or "es")
    band = str(triage.get("band") or "")
    reason = str(audit_row.get("handoff_reason") or "")
    synthetic = bool(packet.get("synthetic_duplicate"))
    return {
        "case_id": row["case_id"],
        "status": row["status"],
        "language": language,
        "band": band,
        "amount": _amount(transaction),
        "currency": str(transaction.get("currency") or ""),
        "merchant": mask_merchant(str(transaction.get("merchant_name") or "")),
        "local_time": str(transaction.get("transaction_ts_customer_local") or ""),
        "reason": reason,
        "reason_label": handoff_reason_label(
            language,
            reason,
            band=band,
            case_type=str(audit_row.get("case_type") or ""),
            synthetic=synthetic,
            card_blocked=_card_blocked(packet),
        ),
        "synthetic_duplicate": synthetic,
        "recommended_next_step": packet.get("recommended_next_step"),
    }


def packet_view(
    row: dict[str, Any],
    audit: dict[str, Any] | None,
    *,
    t_low: float,
    high_value: float,
) -> dict[str, Any]:
    card = queue_card(row, audit)
    packet = _packet(row)
    transaction = _transaction(packet)
    triage = _triage(packet)
    fraud_score = triage.get("fraud_score")
    score = float(fraud_score) if isinstance(fraud_score, (int, float)) else None
    actions = [
        {
            "name": str(item.get("name") or ""),
            "verification_status": str(item.get("verification_status") or ""),
        }
        for item in _actions(packet)
    ]
    return {
        "band": card["band"],
        "model_version": str(triage.get("model_version") or ""),
        "model_risk_score": triage.get("model_risk_score"),
        "fraud_score": score,
        "threshold_crossed": threshold_crossed(
            card["band"], fraud_score=score, t_low=t_low, high_value=high_value
        ),
        "amount": card["amount"],
        "merchant": card["merchant"],
        "local_time": card["local_time"],
        "utc": str(transaction.get("transaction_ts_utc") or ""),
        "customer_tz": str(transaction.get("customer_tz") or ""),
        "actions_taken": actions,
        "reason": card["reason"],
        "reason_label": card["reason_label"],
        "recommended_next_step": card["recommended_next_step"] or "",
    }
