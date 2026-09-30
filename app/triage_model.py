"""TriageModel adapter. HIGH is the fraud_score rule; REVIEW/LOW come from LightGBM.

If the model or the feature row is unavailable, fraud_score > 30 is HIGH and every
other in-scope charge is REVIEW. The fallback never returns LOW.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from app.thresholds_loader import ThresholdConfig, ThresholdSource, is_high_score, preliminary_route


@dataclass(frozen=True)
class TriageScore:
    band: str
    model_risk_score: float | None
    model_version: str
    used_fallback: bool
    saw_model: bool


class TriageModel(Protocol):
    def score(self, row: dict[str, object], config: ThresholdConfig) -> TriageScore: ...


def finite_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


RULE_VERSION = "rule_fs_gt30_v1"
FALLBACK_VERSION = "rule_fs_gt30_v1_fallback"


def _rule_band(row: dict[str, object], config: ThresholdConfig) -> str | None:
    route = preliminary_route(_fraud(row), str(row.get("transaction_status") or ""), config)
    if route == "high":
        return "high"
    if route in {"pending", "reversed"}:
        return "out_of_scope"
    return None


def _fraud(row: dict[str, object]) -> float | None:
    return finite_or_none(row.get("fraud_score"))


class LightGBMTriage:
    """Calls vendored triage.score.score. Thresholds are the caller's current JSON."""

    def score(self, row: dict[str, object], config: ThresholdConfig) -> TriageScore:
        ruled = _rule_band(row, config)
        try:
            prob, band = _call_score(row)
        except Exception as exc:
            if ruled == "high":
                return TriageScore("high", None, RULE_VERSION, used_fallback=False, saw_model=False)
            if ruled == "out_of_scope":
                return TriageScore(
                    "out_of_scope", None, RULE_VERSION, used_fallback=False, saw_model=False
                )
            raise exc
        clean = finite_or_none(prob)
        if ruled == "high":
            return TriageScore(
                "high", None if _is_oos_status(row) else clean, RULE_VERSION, False, True
            )
        if ruled == "out_of_scope":
            return TriageScore("out_of_scope", None, RULE_VERSION, False, True)
        version = f"lgbm:{config.version}"
        if band == "high" and not is_high_score(_fraud(row), config):
            return TriageScore("review", clean, version, used_fallback=False, saw_model=True)
        if band == "low":
            return TriageScore("low", clean, version, False, True)
        if band == "review":
            return TriageScore("review", clean, version, False, True)
        return TriageScore("review", clean, FALLBACK_VERSION, used_fallback=True, saw_model=False)


def _is_oos_status(row: dict[str, object]) -> bool:
    return str(row.get("transaction_status") or "") in {"Pending", "Reversed"}


def _call_score(row: dict[str, object]) -> tuple[object, str]:
    import pandas as pd

    from triage.score import score

    frame = pd.DataFrame([row])
    prob, band = score(frame)
    return prob[0], str(band[0])


class ScriptedTriage:
    """Deterministic stand-in for tests. Honors the same HIGH-first order."""

    def __init__(self, in_scope_bands: dict[str, str] | None = None) -> None:
        self.in_scope_bands = in_scope_bands or {}

    def score(self, row: dict[str, object], config: ThresholdConfig) -> TriageScore:
        ruled = _rule_band(row, config)
        if ruled == "high":
            return TriageScore("high", None, RULE_VERSION, False, True)
        if ruled == "out_of_scope":
            return TriageScore("out_of_scope", None, RULE_VERSION, False, True)
        key = str(row.get("transaction_key") or "")
        band = self.in_scope_bands.get(key, "review")
        if band not in {"low", "review"}:
            band = "review"
        prob = 0.0001 if band == "low" else 0.01
        return TriageScore(band, prob, f"lgbm:{config.version}", False, True)


def fallback_score(row: dict[str, object], config: ThresholdConfig) -> TriageScore:
    if is_high_score(_fraud(row), config):
        return TriageScore("high", None, FALLBACK_VERSION, used_fallback=True, saw_model=False)
    if _is_oos_status(row):
        return TriageScore(
            "out_of_scope", None, FALLBACK_VERSION, used_fallback=True, saw_model=False
        )
    return TriageScore("review", None, FALLBACK_VERSION, used_fallback=True, saw_model=False)


def score_with_fallback(
    model: TriageModel,
    row: dict[str, object],
    source: ThresholdSource,
) -> tuple[TriageScore, ThresholdConfig, bool]:
    """Returns score, thresholds, and whether the model band disagreed with the rule order."""
    config = source.get()
    try:
        scored = model.score(row, config)
    except Exception:
        scored = fallback_score(row, config)
    expected = _rule_band(row, config)
    mismatch = False
    if expected == "high" and scored.band != "high":
        mismatch = True
        scored = TriageScore("high", None, RULE_VERSION, scored.used_fallback, scored.saw_model)
    elif expected == "out_of_scope" and scored.band not in {"out_of_scope", "high"}:
        mismatch = True
        scored = TriageScore(
            "out_of_scope", None, scored.model_version, scored.used_fallback, scored.saw_model
        )
    elif expected is None and scored.band == "high":
        mismatch = True
        scored = TriageScore(
            "review", scored.model_risk_score, scored.model_version, True, scored.saw_model
        )
    elif expected is None and scored.band == "low" and scored.used_fallback:
        mismatch = True
        scored = TriageScore("review", None, FALLBACK_VERSION, True, False)
    return scored, config, mismatch
