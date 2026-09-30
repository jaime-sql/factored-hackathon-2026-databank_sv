"""App-facing scoring for the fraud-risk triage model (frozen from TRAIN/VAL on 2026-09-29).

    from triage.score import score
    prob, band = score(df)   # df: one row per transaction with the manifest feature columns

- prob: calibrated fraud probability when calibrator.joblib is present; otherwise the raw score
- band (v2 banding, team decision 2026-09-29):
        'high'   -> fraud_score > 30 (deterministic rule; missing fraud_score is never HIGH)
        'review' -> not HIGH and LightGBM raw score >= t_low
        'low'    -> not HIGH and raw score < t_low
        'out_of_scope' -> Pending/Reversed AND fraud_score is not > 30
  Order: the HIGH rule runs BEFORE the Pending/Reversed shortcut.
  prob is NaN for Pending/Reversed rows.
Thresholds are re-read from artifacts/thresholds.json on every call so a replaced file is picked up.
The booster stays cached. calibrator.joblib is optional; without it calibration is the identity.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ART = Path(__file__).resolve().parent / "artifacts"
OUT_OF_SCOPE_STATUSES = {"Pending", "Reversed"}


def _thresholds() -> dict:
    return json.loads((ART / "thresholds.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_static() -> dict:
    feats = json.loads((ART / "feature_list.json").read_text(encoding="utf-8"))
    calibrator: dict = {"method": "none", "model": None}
    cal_path = ART / "calibrator.joblib"
    if cal_path.exists():
        import joblib

        loaded = joblib.load(cal_path)
        if isinstance(loaded, dict):
            calibrator = loaded
    return {
        "booster": lgb.Booster(model_file=str(ART / "model.txt")),
        "calibrator": calibrator,
        "features": feats["features"],
        "categorical": set(feats["categorical"]),
        "cat_maps": json.loads((ART / "category_mappings.json").read_text(encoding="utf-8")),
    }


def _load() -> dict:
    """Booster cache plus the thresholds file as it exists right now."""
    data = dict(_load_static())
    data["thresholds"] = _thresholds()
    return data


def _matrix(df: pd.DataFrame, art: dict) -> pd.DataFrame:
    missing = [col for col in art["features"] if col not in df.columns]
    if missing:
        raise KeyError(f"missing feature columns: {missing}")
    out = {}
    for col in art["features"]:
        if col in art["categorical"]:
            series = df[col].astype("object")
            allowed = art["cat_maps"][col]
            # Unknown labels become missing, which is how the booster already treats them.
            series = series.where(series.isin(allowed), None)
            out[col] = pd.Categorical(series, categories=allowed)
        else:
            out[col] = pd.to_numeric(df[col].astype("object"), errors="coerce").astype("float32")
    return pd.DataFrame(out, index=df.index)


def score_raw(df: pd.DataFrame) -> np.ndarray:
    art = _load()
    return art["booster"].predict(_matrix(df, art))


def calibrate(raw) -> np.ndarray:
    calibrator = _load()["calibrator"]
    raw_arr = np.asarray(raw, dtype="float64")
    if calibrator["method"] == "none" or calibrator["model"] is None:
        return raw_arr
    if calibrator["method"] == "platt":
        clipped = np.clip(raw_arr, 1e-9, 1 - 1e-9)
        return calibrator["model"].predict_proba(np.log(clipped / (1 - clipped)).reshape(-1, 1))[
            :, 1
        ]
    return calibrator["model"].predict(raw_arr)


def high_mask(fraud_score) -> np.ndarray:
    rule = _thresholds()["high_rule"]
    if rule["op"] != ">" or rule["missing"] != "not HIGH":
        raise ValueError("unsupported high_rule; expected op '>' and missing 'not HIGH'")
    scores = pd.to_numeric(pd.Series(fraud_score).astype("object"), errors="coerce").to_numpy(
        dtype="float64"
    )
    return np.nan_to_num(scores, nan=-np.inf) > float(rule["value"])


def band_of(raw, fraud_score) -> np.ndarray:
    thresholds = _thresholds()
    scores = np.nan_to_num(np.asarray(raw, dtype="float64"), nan=-np.inf)
    return np.where(
        high_mask(fraud_score),
        "high",
        np.where(scores >= thresholds["t_low"], "review", "low"),
    ).astype(object)


def score(df: pd.DataFrame):
    """Return (prob, band) as numpy arrays aligned with df rows."""
    fraud_scores = df["fraud_score"].to_numpy()
    count = len(df)
    if "transaction_status" in df.columns:
        out_of_scope = df["transaction_status"].isin(OUT_OF_SCOPE_STATUSES).to_numpy()
    else:
        out_of_scope = np.zeros(count, dtype=bool)
    prob = np.full(count, np.nan)
    band = np.empty(count, dtype=object)
    if (~out_of_scope).any():
        subset = df.loc[~out_of_scope]
        raw = score_raw(subset)
        prob[~out_of_scope] = calibrate(raw)
        band[~out_of_scope] = band_of(raw, subset["fraud_score"].to_numpy())
    if out_of_scope.any():
        band[out_of_scope] = np.where(high_mask(fraud_scores[out_of_scope]), "high", "out_of_scope")
    return prob, band
