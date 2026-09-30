"""Load triage thresholds from JSON. Re-read when the file changes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ThresholdConfig:
    version: str
    high_op: str
    high_value: float
    t_low: float
    out_of_scope_statuses: frozenset[str]
    path: str


def load_thresholds(path: Path) -> ThresholdConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rule = raw["high_rule"]
    if rule.get("op") != ">" or rule.get("missing") != "not HIGH":
        raise ValueError("thresholds high_rule must be fraud_score > value, missing is not HIGH")
    status_rule = raw.get("status_rule", {})
    statuses = frozenset(status_rule.get("out_of_scope_statuses", ["Pending", "Reversed"]))
    return ThresholdConfig(
        version=str(raw.get("version", "unknown")),
        high_op=">",
        high_value=float(rule["value"]),
        t_low=float(raw["t_low"]),
        out_of_scope_statuses=statuses,
        path=str(path),
    )


class ThresholdSource:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._mtime_ns: int | None = None
        self._config: ThresholdConfig | None = None

    def get(self) -> ThresholdConfig:
        mtime_ns = self.path.stat().st_mtime_ns
        if self._config is None or mtime_ns != self._mtime_ns:
            self._config = load_thresholds(self.path)
            self._mtime_ns = mtime_ns
        return self._config


def is_high_score(fraud_score: float | None, config: ThresholdConfig) -> bool:
    if fraud_score is None:
        return False
    if fraud_score != fraud_score:  # NaN
        return False
    return fraud_score > config.high_value


def preliminary_route(fraud_score: float | None, status: str, config: ThresholdConfig) -> str:
    """App routing order, matching thresholds.status_rule.

    Returns high, pending, reversed, or in_scope.
    """
    if is_high_score(fraud_score, config):
        return "high"
    if status in config.out_of_scope_statuses and status == "Pending":
        return "pending"
    if status in config.out_of_scope_statuses and status == "Reversed":
        return "reversed"
    if status in config.out_of_scope_statuses:
        return "pending"
    return "in_scope"
