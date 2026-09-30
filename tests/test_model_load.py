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


# Raw scores recorded before unknown categories were coerced to missing.
_UNCHANGED_RAW = {
    "smoke": 0.0003102440188673794,
    "tx_lucia_source": 0.0002617090698935654,
    "tx_maria_low": 0.0003839153099521331,
}


def test_unknown_categories_keep_the_same_scores() -> None:
    import warnings

    from app.bank.fixture import build_rows

    _transactions, features, _duplicates = build_rows()
    rows = {"smoke": _fixture_row()}
    for key in ("tx_lucia_source", "tx_maria_low"):
        rows[key] = next(row for row in features if row["transaction_key"] == key)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        from triage.score import score_raw

        for name, row in rows.items():
            raw = score_raw(pd.DataFrame([row]))
            assert float(raw[0]) == _UNCHANGED_RAW[name]
    assert not any("Categorical" in str(item.message) for item in caught)
