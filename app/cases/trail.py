"""Why-trail for one case.

The tip is `audit_current`. Older decisions are the read-only parents linked by
supersedes_audit_id. Tool rows come from audit_event. Nothing here is updated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.guardrails.pii import redact
from app.i18n import handoff_reason_label, threshold_crossed, trail_customer_reason
from app.timeutil import as_utc, present_time

_HIGH_STATUS = {
    "awaiting_block_confirmation",
    "blocked_and_handed_off",
    "block_unverified_handed_off",
    "declined_block_handed_off",
}
_LOW_STATUS = {"merchant_explained", "duplicate_explained", "merchant_recognized"}
_SCOPE_STATUS = {"pending_explained", "reversed_explained", "contested_rule_handed_off"}


def _stamp(value: object) -> datetime:
    try:
        return as_utc(value)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=UTC)


def _score(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(str(value))
        except ValueError:
            return None
    if number != number:
        return None
    return number


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def infer_band(row: dict[str, Any]) -> str:
    reason = _text(row.get("handoff_reason"))
    status = _text(row.get("final_resolution_status"))
    flags = {str(flag) for flag in row.get("guardrail_flags") or []}
    if reason == "fraud_rule" or status in _HIGH_STATUS:
        return "high"
    if reason == "fraud_model":
        return "review"
    if reason == "customer_requested_human" or status in _LOW_STATUS:
        return "low"
    if (
        reason in {"customer_contests_rule_answer", "prompt_injection", "injection_detected"}
        or status in _SCOPE_STATUS
        or status == "injection_blocked"
        or "prompt_injection" in flags
        or "injection_detected" in flags
    ):
        return "out_of_scope"
    case_type = _text(row.get("case_type"))
    if case_type in {"pending", "reversed"}:
        return "out_of_scope"
    return ""


def _card_blocked(events: list[dict[str, Any]], at: datetime) -> bool:
    for event in events:
        if event.get("kind") != "tool" or event.get("name") != "block_card":
            continue
        if _text(event.get("verification_status")) != "verified":
            continue
        if _stamp(event.get("recorded_at")) <= at:
            return True
    return False


def _clean(value: str) -> str:
    return redact(value)


def build_steps(
    audits: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    tz: str | None,
    country: str | None,
    language: str,
    t_low: float,
    high_value: float,
    safe: bool,
) -> list[dict[str, Any]]:
    """Chronological decisions, plus tool actions on the agent trail."""
    items: list[tuple[datetime, int, dict[str, Any]]] = []
    for audit in audits:
        at = _stamp(audit.get("recorded_at"))
        band = infer_band(audit)
        reason = _text(audit.get("handoff_reason"))
        status = _text(audit.get("final_resolution_status"))
        case_type = _text(audit.get("case_type"))
        blocked = _card_blocked(events, at)
        label = trail_customer_reason(
            language,
            reason=reason,
            status=status,
            band=band,
            case_type=case_type,
            card_blocked=blocked,
        )
        if not safe and reason == "fraud_model":
            label = handoff_reason_label(
                language,
                reason,
                band=band,
                case_type=case_type,
                synthetic=False,
                card_blocked=blocked,
            )
        shown = present_time(at, tz, country, language)
        if safe:
            items.append(
                (
                    at,
                    0,
                    {
                        "at": _clean(shown["label"]),
                        "band": band,
                        "reason": _clean(label),
                    },
                )
            )
            continue
        flags = [_clean(str(flag)) for flag in audit.get("guardrail_flags") or []]
        score = _score(audit.get("fraud_score"))
        items.append(
            (
                at,
                0,
                {
                    "kind": "decision",
                    "at": _clean(shown["label"]),
                    "utc": shown["utc"],
                    "rule_or_model": _clean(_text(audit.get("rule_or_model_version"))),
                    "band": band,
                    "threshold": threshold_crossed(
                        band, fraud_score=score, t_low=t_low, high_value=high_value
                    ),
                    "guardrail_flags": flags,
                    "handoff": _clean(_text(audit.get("decision"))),
                    "reason": _clean(reason),
                    "reason_label": _clean(label),
                },
            )
        )
    if not safe:
        for index, event in enumerate(events):
            if event.get("kind") != "tool":
                continue
            at = _stamp(event.get("recorded_at"))
            shown = present_time(at, tz, country, language)
            items.append(
                (
                    at,
                    index + 1,
                    {
                        "kind": "action",
                        "at": _clean(shown["label"]),
                        "utc": shown["utc"],
                        "action": _clean(_text(event.get("name"))),
                        "verification": _clean(_text(event.get("verification_status"))),
                    },
                )
            )
    items.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in items]
