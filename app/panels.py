"""Optional JSON panels served from static/data.

Missing files stay hidden. Cost-per-case is rendered only after Analytics adds it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.paths import project_root

_COST_KEYS = ("cost_per_case", "cost_per_case_usd", "expected_cost_usd", "cost_usd")


def read_data_file(name: str, root: Path | None = None) -> Any:
    path = (root or project_root()) / "static" / "data" / name
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def trust_panel(root: Path | None = None) -> list[dict[str, Any]] | None:
    payload = read_data_file("trust.json", root)
    if not isinstance(payload, list):
        return None
    rows = [item for item in payload if isinstance(item, dict)]
    return rows or None


def simulator_panel(root: Path | None = None) -> dict[str, Any] | None:
    payload = read_data_file("sim_curve.json", root)
    if not isinstance(payload, dict):
        return None
    points = payload.get("points")
    if not isinstance(points, list):
        return None
    show_cost = False
    for point in points:
        if not isinstance(point, dict):
            continue
        if any(point.get(key) is not None for key in _COST_KEYS):
            show_cost = True
            break
    return {**payload, "show_cost": show_cost}


def fairness_panel(root: Path | None = None) -> Any:
    payload = read_data_file("fairness.json", root)
    if isinstance(payload, (dict, list)) and payload:
        return payload
    return None
