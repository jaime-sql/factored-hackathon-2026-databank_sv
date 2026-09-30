"""The vendored booster must load. A silent fallback hides LOW and the duplicate reply."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "triage" / "artifacts" / "model.txt"


def _fixture_row() -> dict[str, object]:
    features = json.loads((ROOT / "triage" / "artifacts" / "feature_list.json").read_text())
    maps = json.loads((ROOT / "triage" / "artifacts" / "category_mappings.json").read_text())
    numeric = set(features["numeric"])
    row: dict[str, object] = {}
    for name in features["features"]:
        if name in numeric:
            row[name] = 1.0
        else:
            row[name] = maps[name][0]
    row["fraud_score"] = 1.0
    row["transaction_status"] = "Approved"
    row["transaction_key"] = "tx_model_smoke"
    return row


def test_lightgbm_loads_when_model_file_is_present() -> None:
    if not MODEL.is_file():
        pytest.fail("triage/artifacts/model.txt is missing; scoring would fall back to REVIEW")
    from app.thresholds_loader import ThresholdSource
    from app.triage_model import LightGBMTriage
    from triage.score import band_of, score_raw

    frame = pd.DataFrame([_fixture_row()])
    raw = score_raw(frame)
    assert raw.shape == (1,)
    assert np.isfinite(raw[0])

    config = ThresholdSource(ROOT / "triage" / "artifacts" / "thresholds.json").get()
    scored = LightGBMTriage().score(_fixture_row(), config)
    assert scored.saw_model is True
    assert scored.used_fallback is False
    assert scored.model_version.startswith("lgbm:")
    assert scored.band in {"low", "review"}

    # Live e2e anchors: these raw scores sit on either side of t_low 0.0002756.
    assert band_of(np.array([0.000257]), np.array([1.0]))[0] == "low"
    assert band_of(np.array([0.00101]), np.array([1.0]))[0] == "review"
