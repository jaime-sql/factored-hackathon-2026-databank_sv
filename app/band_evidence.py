"""Load per-band validation evidence. Missing or incomplete data stays hidden.

`triage/artifacts/band_evidence.json` is produced by the ML engineer. This module
never fills in a threshold, a fraud rate, or a confidence interval. Rates in the
file are proportions in [0, 1] (0.012 is shown as 1.2%).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BandEvidence:
    band: str
    threshold: float
    val_fraud_rate: float
    ci_low: float
    ci_high: float


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
    else:
        return None
    if number != number:
        return None
    return number


def _interval(item: dict[str, Any]) -> tuple[float, float] | None:
    ci = item.get("ci")
    if isinstance(ci, (list, tuple)) and len(ci) == 2:
        low = _number(ci[0])
        high = _number(ci[1])
    else:
        low = _number(item.get("ci_low"))
        high = _number(item.get("ci_high"))
    if low is None or high is None:
        return None
    return low, high


def _bands(raw: object) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    bands = raw.get("bands")
    found: dict[str, dict[str, Any]] = {}
    if isinstance(bands, dict):
        for key, item in bands.items():
            if isinstance(item, dict):
                found[str(key)] = item
        return found
    if isinstance(bands, list):
        for item in bands:
            if isinstance(item, dict) and item.get("band"):
                found[str(item["band"])] = item
    return found


class BandEvidenceSource:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get(self, band: str) -> BandEvidence | None:
        if not band or not self.path.is_file():
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        item = _bands(raw).get(band)
        if item is None:
            return None
        threshold = _number(item.get("threshold"))
        rate = _number(item.get("val_fraud_rate"))
        interval = _interval(item)
        if threshold is None or rate is None or interval is None:
            return None
        return BandEvidence(band, threshold, rate, interval[0], interval[1])

    def line(self, band: str) -> str | None:
        evidence = self.get(band)
        if evidence is None:
            return None
        rate = evidence.val_fraud_rate * 100
        low = evidence.ci_low * 100
        high = evidence.ci_high * 100
        return (
            f"band {evidence.band}, crossed threshold {evidence.threshold:.7g}, "
            f"fraud rate in this band on val {rate:.1f}% (CI {low:.1f}–{high:.1f}%)"
        )
