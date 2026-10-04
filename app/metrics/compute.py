"""Operational KPIs.

The default row set is audit_live. include_test and include_eval read
audit_current and apply only the filters that were not requested. The toggle
label is the demo-sample warning. Safe-automation and unsafe rates need
eval.case_labels, which this process does not read.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from app.eval_access import DEMO_SAMPLE_LABEL
from app.ops.console_action import is_console_decision


def _eval_traffic(row: dict[str, Any]) -> bool:
    return row.get("eval_run_id") not in (None, "")


def _test_traffic(row: dict[str, Any], test_ids: set[str]) -> bool:
    return bool(row.get("is_test")) or str(row.get("case_id") or "") in test_ids


def _demo_attack(row: dict[str, Any]) -> bool:
    return bool(row.get("demo_attack"))


def _agent_explained(row: dict[str, Any]) -> bool:
    return (
        row.get("source") == "agent"
        and row.get("decision") == "auto_resolved"
        and row.get("final_resolution_status") in {"pending_explained", "reversed_explained"}
    )


def select_cases(
    cases: list[dict[str, Any]],
    *,
    include_eval: bool,
    include_test: bool,
    test_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Drop eval and test rows unless the caller asked to keep them.

    Eval traffic is an audit tip whose eval_run_id is set. Test traffic is an
    is_test tip or a case id listed in test_cases.
    """
    marked = test_ids or set()
    chosen: list[dict[str, Any]] = []
    for row in cases:
        if _demo_attack(row):
            continue
        if _eval_traffic(row) and not include_eval:
            continue
        if _test_traffic(row, marked) and not include_test:
            continue
        chosen.append(row)
    kept = {id(row) for row in chosen}
    excluded_eval = sum(1 for row in cases if _eval_traffic(row) and id(row) not in kept)
    excluded_test = sum(1 for row in cases if _test_traffic(row, marked) and id(row) not in kept)
    return chosen, excluded_eval, excluded_test


def compute_metrics(
    cases: list[dict[str, Any]],
    calls: list[dict[str, Any]],
    prices: list[dict[str, Any]],
    assumptions: dict[str, float],
    *,
    include_eval: bool,
    include_test: bool = False,
    test_ids: set[str] | None = None,
    excluded_eval: int | None = None,
    excluded_test: int | None = None,
) -> dict[str, Any]:
    if excluded_eval is None or excluded_test is None:
        chosen, excluded_eval, excluded_test = select_cases(
            cases,
            include_eval=include_eval,
            include_test=include_test,
            test_ids=test_ids,
        )
    else:
        chosen = list(cases)
    # Console tips stay in audit_live. Volume and rates stay on the routing tip.
    chosen = [row for row in chosen if not is_console_decision(row.get("decision"))]
    chosen_ids = {row["case_id"] for row in chosen}
    chosen_calls = [row for row in calls if row.get("case_id") in chosen_ids]
    # Captain's definition: contained = closed without a handoff / closed. A case waiting
    # on the customer (final_resolution_status 'clarifying') is not closed, so it is in
    # neither number; it counts as still open.
    waiting = [row for row in chosen if row.get("final_resolution_status") == "clarifying"]
    closed = [
        row
        for row in chosen
        if row.get("decision") and row.get("final_resolution_status") != "clarifying"
    ]
    volume: dict[str, int] = {}
    for row in chosen:
        key = str(row.get("case_type") or "other")
        volume[key] = volume.get(key, 0) + 1
    total = len(chosen)
    in_scope = [row for row in closed if row.get("case_type") != "other"]
    attempted = [row for row in in_scope if row.get("automation_attempted")]
    handoffs = [row for row in closed if row.get("decision") == "handoff"]
    reasons: dict[str, int] = {}
    for row in handoffs:
        reason = str(row.get("handoff_reason") or "unspecified")
        reasons[reason] = reasons.get(reason, 0) + 1
    # Analytics: a pending or reversed charge the AI agent explained and closed is its own
    # line (ai_resolved). It stays out of dispute containment so it cannot inflate it.
    ai_resolved = [row for row in closed if _agent_explained(row)]
    dispute_closed = [row for row in closed if not _agent_explained(row)]
    contained = [row for row in dispute_closed if row.get("decision") != "handoff"]
    open_cases = [row for row in chosen if not row.get("decision")] + waiting
    durations = _durations(closed)
    latencies = [int(row.get("latency_ms") or 0) for row in chosen_calls]
    failed_calls = [row for row in chosen_calls if row.get("call_status") != "ok"]
    costs = [_case_cost(row, chosen_calls, prices) for row in chosen]
    mean_cost = sum(costs) / len(costs) if costs else None
    health = _llm_health(chosen_calls, prices)
    return {
        "include_eval": include_eval,
        "include_test": include_test,
        "eval_toggle_label": DEMO_SAMPLE_LABEL,
        "excluded_eval_cases": excluded_eval,
        "excluded_test_cases": excluded_test,
        "still_open": len(open_cases),
        "k1_volume": {
            "total": total,
            "by_case_type": [
                {"case_type": name, "count": count, "share": _share(count, total)}
                for name, count in sorted(volume.items())
            ],
        },
        "k2_automation_attempted": _rate(len(attempted), len(in_scope)),
        "k3_safe_automated_resolution": {
            "value": "offline",
            "note": "Requires eval.case_labels. This console role cannot read the eval schema.",
        },
        "k4_unsafe": {
            "value": "offline",
            "note": "Requires eval.case_labels. This console role cannot read the eval schema.",
        },
        "k5_handoff": {
            **_rate(len(handoffs), len(closed)),
            "reasons": [
                {"reason": name, "count": count} for name, count in sorted(reasons.items())
            ],
            "packet_complete": _rate(
                sum(1 for row in handoffs if row.get("handoff_packet_complete")),
                len(handoffs),
            ),
        },
        "k6_containment": _rate(len(contained), len(dispute_closed)),
        "ai_resolved": {
            "count": len(ai_resolved),
            "agent_closed": sum(1 for row in closed if row.get("source") == "agent"),
            "note": "Pending or reversed charges the AI agent explained and closed. "
            "Not part of containment.",
        },
        "k7_time_to_resolution": {
            "p50_s": _percentile(durations, 0.5),
            "p90_s": _percentile(durations, 0.9),
            "p95_s": _percentile(durations, 0.95),
            "n": len(durations),
            "still_open": len(open_cases),
        },
        "k8_latency_ms": {
            "p50": _percentile(latencies, 0.5),
            "p90": _percentile(latencies, 0.9),
            "p95": _percentile(latencies, 0.95),
            "n": len(latencies),
            "error_rate": _rate(len(failed_calls), len(chosen_calls)),
        },
        "k9_cost_usd": {
            "per_case": None if mean_cost is None else round(mean_cost, 4),
            "per_safe_resolution": "not defined",
            "n": len(chosen),
        },
        "k10_projection": _projection(assumptions),
        "k11_fairness_handoff": _fairness(closed),
        "k12_guardrails": _guardrails(chosen),
        "k13_reliability": {
            "llm_error": _rate(len(failed_calls), len(chosen_calls)),
            "fallback_used": _rate(
                sum(1 for row in chosen if "fallback_used" in (row.get("guardrail_flags") or [])),
                len(chosen),
            ),
        },
        "rates_note": (
            "Rates use closed cases. Open cases are counted as still_open and are not mixed in."
        ),
        "small_sample_rule": "n < 30 is not reliable",
        "health": health,
    }


def _llm_health(calls: list[dict[str, Any]], prices: list[dict[str, Any]]) -> dict[str, Any]:
    """p50/p95 latency and mean cost for the same live calls as the other tiles."""
    latencies = [int(row.get("latency_ms") or 0) for row in calls]
    priced: list[float] = []
    for call in calls:
        price = _price_for(str(call.get("model") or ""), call.get("call_started_at"), prices)
        if price is None:
            continue
        priced.append(
            int(call.get("input_tokens") or 0) * price[0] / 1_000_000
            + int(call.get("output_tokens") or 0) * price[1] / 1_000_000
        )
    mean = round(sum(priced) / len(priced), 6) if priced else None
    return {
        "llm_calls": len(calls),
        "latency_p50_ms": _percentile(latencies, 0.5),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "mean_cost_per_call_usd": mean,
    }


def _rate(k: int, n: int) -> dict[str, Any]:
    if n == 0:
        return {"k": k, "n": n, "pct": None, "display": "not defined", "reliable": False}
    pct = round(100.0 * k / n, 1)
    return {
        "k": k,
        "n": n,
        "pct": pct,
        "display": f"{k} / {n}",
        "reliable": n >= 30,
    }


def _share(count: int, total: int) -> float | None:
    if total == 0:
        return None
    return round(count / total, 3)


def _percentile(values: list[float] | list[int], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return ordered[low]
    weight = pos - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _parse_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def _durations(rows: list[dict[str, Any]]) -> list[float]:
    found: list[float] = []
    for row in rows:
        start = _parse_time(row.get("case_created_at"))
        end = _parse_time(row.get("case_closed_at"))
        if start is None or end is None:
            continue
        found.append((end - start).total_seconds())
    return found


def _case_cost(
    case: dict[str, Any], calls: list[dict[str, Any]], prices: list[dict[str, Any]]
) -> float:
    total = 0.0
    for call in calls:
        if call.get("case_id") != case.get("case_id"):
            continue
        price = _price_for(str(call.get("model") or ""), call.get("call_started_at"), prices)
        if price is None:
            continue
        total += (
            int(call.get("input_tokens") or 0) * price[0] / 1_000_000
            + int(call.get("output_tokens") or 0) * price[1] / 1_000_000
        )
    return total


def _price_for(
    model: str,
    started: object,
    prices: list[dict[str, Any]],
) -> tuple[float, float] | None:
    started_at = _parse_time(started)
    best: tuple[str, float, float] | None = None
    for row in prices:
        if str(row.get("model")) != model:
            continue
        effective = str(row.get("effective_from"))
        if started_at is not None and effective > started_at.date().isoformat():
            continue
        if best is None or effective > best[0]:
            best = (effective, float(row["usd_per_1m_input"]), float(row["usd_per_1m_output"]))
    if best is None:
        return None
    return best[1], best[2]


def _projection(assumptions: dict[str, float]) -> dict[str, Any]:
    seconds = assumptions.get("queja_handle_seconds", 434.6)
    scenarios = []
    for name, key in (
        ("low", "wage_low_usd_per_hour"),
        ("mid", "wage_mid_usd_per_hour"),
        ("high", "wage_high_usd_per_hour"),
    ):
        wage = assumptions.get(key, 0)
        scenarios.append(
            {
                "scenario": name,
                "wage_usd_per_hour": wage,
                "cost_per_contact_usd": round(seconds / 3600 * wage, 2),
                "result": "not defined",
            }
        )
    return {
        "label": "PROJECTION",
        "note": "PROJECTION: wage rates assumed. The safe-automated numerator is offline.",
        "scenarios": scenarios,
        "disputes_per_month": assumptions.get("disputes_per_month"),
    }


def _guardrails(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        for flag in row.get("guardrail_flags") or []:
            counts[str(flag)] = counts.get(str(flag), 0) + 1
    n = len(rows)
    return [
        {
            "flag": name,
            "events": count,
            "per_100_cases": None if n == 0 else round(100.0 * count / n, 2),
        }
        for name, count in sorted(counts.items(), key=lambda item: -item[1])
    ]


def _fairness(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slices: list[dict[str, Any]] = []
    for dimension, field in (
        ("country", "country"),
        ("segment", "customer_segment"),
        ("language", "language"),
    ):
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = str(row.get(field) or "unknown")
            groups.setdefault(key, []).append(row)
        rates = []
        for name, group in sorted(groups.items()):
            handoff = sum(1 for row in group if row.get("decision") == "handoff")
            rates.append({"group": name, **_rate(handoff, len(group)), "dimension": dimension})
        eligible = [item["pct"] for item in rates if item["n"] >= 30 and item["pct"] is not None]
        gap = None if len(eligible) < 2 else max(eligible) - min(eligible)
        slices.append(
            {
                "dimension": dimension,
                "groups": rates,
                "disparity_gap_pts": None if gap is None else round(gap, 1),
                "disparity_flag_heuristic": bool(gap is not None and gap > 5),
                "language_note": (
                    "Portuguese rows are machine-translated test cases, not production traffic."
                    if dimension == "language"
                    else None
                ),
            }
        )
    return slices
