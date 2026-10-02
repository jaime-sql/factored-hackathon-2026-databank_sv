"""Queue cards and the expanded handoff view. No raw customer text."""

from __future__ import annotations

from typing import Any

from app.i18n import (
    display_next_step,
    handoff_reason_label,
    localize_stored_merchant,
    mask_merchant,
    money,
    score_line,
    threshold_crossed,
)
from app.timeutil import present_time


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


def _amount(transaction: dict[str, Any], country: str) -> str:
    raw = transaction.get("amount")
    currency = str(transaction.get("currency") or "")
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return currency
    try:
        amount = float(raw)
    except ValueError:
        return currency
    return money(amount, currency, country)


def _display_language(packet: dict[str, Any], display_language: str | None) -> str:
    if display_language in {"es", "pt"}:
        return display_language
    stored = str(packet.get("language") or "es")
    return stored if stored in {"es", "pt"} else "es"


def _local_label(transaction: dict[str, Any], language: str) -> str:
    fallback = str(transaction.get("transaction_ts_customer_local") or "")
    utc = transaction.get("transaction_ts_utc")
    if not utc:
        return fallback
    try:
        return present_time(
            utc,
            str(transaction.get("customer_tz") or "") or None,
            str(transaction.get("transaction_country") or "") or None,
            language,
        )["label"]
    except (TypeError, ValueError):
        return fallback


def queue_card(
    row: dict[str, Any],
    audit: dict[str, Any] | None,
    *,
    display_language: str | None = None,
) -> dict[str, Any]:
    packet = _packet(row)
    transaction = _transaction(packet)
    triage = _triage(packet)
    audit_row = audit or {}
    language = _display_language(packet, display_language)
    country = str(audit_row.get("country") or "")
    band = str(triage.get("band") or "")
    reason = str(audit_row.get("handoff_reason") or "")
    synthetic = bool(packet.get("synthetic_duplicate"))
    blocked = _card_blocked(packet)
    merchant = localize_stored_merchant(language, str(transaction.get("merchant_name") or ""))
    stored_step = str(packet.get("recommended_next_step") or "")
    return {
        "case_id": row["case_id"],
        "status": row["status"],
        "language": language,
        "band": band,
        "amount": _amount(transaction, country),
        "currency": str(transaction.get("currency") or ""),
        "merchant": mask_merchant(merchant),
        "local_time": _local_label(transaction, language),
        "reason": reason,
        "reason_label": handoff_reason_label(
            language,
            reason,
            band=band,
            case_type=str(audit_row.get("case_type") or ""),
            synthetic=synthetic,
            card_blocked=blocked,
        ),
        "synthetic_duplicate": synthetic,
        "is_test": bool(audit_row.get("is_test")),
        "recommended_next_step": display_next_step(
            language, reason, card_blocked=blocked, stored=stored_step
        ),
    }


def packet_view(
    row: dict[str, Any],
    audit: dict[str, Any] | None,
    *,
    t_low: float,
    high_value: float,
    display_language: str | None = None,
) -> dict[str, Any]:
    card = queue_card(row, audit, display_language=display_language)
    packet = _packet(row)
    transaction = _transaction(packet)
    triage = _triage(packet)
    fraud_score = triage.get("fraud_score")
    score = (
        float(fraud_score)
        if isinstance(fraud_score, (int, float)) and not isinstance(fraud_score, bool)
        else None
    )
    risk = triage.get("model_risk_score")
    risk_score = (
        float(risk) if isinstance(risk, (int, float)) and not isinstance(risk, bool) else None
    )
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
        "model_risk_score": risk_score,
        "fraud_score": score,
        "t_low": t_low,
        "high_value": high_value,
        "threshold_crossed": threshold_crossed(
            card["band"], fraud_score=score, t_low=t_low, high_value=high_value
        ),
        "score_line": score_line(
            card["language"],
            card["band"],
            model_risk_score=risk_score,
            fraud_score=score,
            t_low=t_low,
            high_value=high_value,
        ),
        "amount": card["amount"],
        "merchant": card["merchant"],
        "local_time": card["local_time"],
        "utc": str(transaction.get("transaction_ts_utc") or ""),
        "customer_tz": str(transaction.get("customer_tz") or ""),
        "actions_taken": actions,
        "reason": card["reason"],
        "reason_label": card["reason_label"],
        "is_test": card["is_test"],
        "recommended_next_step": card["recommended_next_step"] or "",
    }
