"""App-facing scoring for the fraud-risk triage model (frozen from TRAIN/VAL on 2026-09-29).

    from triage.score import score
    prob, band = score(df)   # df: one row per transaction with the manifest feature columns

- prob: calibrated fraud probability (calibrator fitted on VAL; see artifacts/thresholds.json)
- band (v2 banding, team decision 2026-09-29):
        'high'   -> fraud_score > 30 (deterministic rule; missing fraud_score is never HIGH)
                    -> offer card block (with customer confirmation) + human handoff
        'review' -> not HIGH and LightGBM raw score >= t_low -> human handoff (review), no block
        'low'    -> not HIGH and raw score < t_low -> agent auto-explains / helps identify merchant, may close
        'out_of_scope' -> transaction_status is Pending/Reversed AND fraud_score is not > 30
                          (deterministic rule-based answer; only if a transaction_status column is supplied)
  Order (team decision 2026-09-29): the HIGH rule fraud_score > 30 runs BEFORE the Pending/Reversed
  shortcut, so a Pending/Reversed charge with fraud_score > 30 is 'high'.
  prob is NaN for Pending/Reversed rows (the model was trained only on Approved/Declined); their
  model feature columns may therefore be absent/NaN.
t_low is on the raw model score (calibration is monotone and only changes the displayed
probability). Self-contained: only reads files in ../artifacts.
Self-test on VAL (never TEST):  .venv/bin/python -m triage.score --selftest
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

ART = Path(__file__).resolve().parent.parent / "artifacts"
OUT_OF_SCOPE_STATUSES = {"Pending", "Reversed"}


@lru_cache(maxsize=1)
def _load():
    feats = json.loads((ART / "feature_list.json").read_text())
    return dict(
        booster=lgb.Booster(model_file=str(ART / "model.txt")),
        calibrator=joblib.load(ART / "calibrator.joblib"),
        features=feats["features"],
        categorical=set(feats["categorical"]),
        cat_maps=json.loads((ART / "category_mappings.json").read_text()),
        thresholds=json.loads((ART / "thresholds.json").read_text()),
    )


def _matrix(df: pd.DataFrame, a: dict) -> pd.DataFrame:
    missing = [c for c in a["features"] if c not in df.columns]
    if missing:
        raise KeyError(f"missing feature columns: {missing}")
    out = {}
    for c in a["features"]:
        if c in a["categorical"]:
            s = df[c].astype("object").where(df[c].notna(), None)
            out[c] = pd.Categorical(
                s, categories=a["cat_maps"][c]
            )  # unseen -> NaN (treated as missing)
        else:
            out[c] = pd.to_numeric(df[c].astype("object"), errors="coerce").astype("float32")
    return pd.DataFrame(out, index=df.index)


def score_raw(df: pd.DataFrame) -> np.ndarray:
    a = _load()
    return a["booster"].predict(_matrix(df, a))


def calibrate(raw) -> np.ndarray:
    c = _load()["calibrator"]
    raw = np.asarray(raw, dtype="float64")
    if c["method"] == "none" or c["model"] is None:
        return raw
    if c["method"] == "platt":
        p = np.clip(raw, 1e-9, 1 - 1e-9)
        return c["model"].predict_proba(np.log(p / (1 - p)).reshape(-1, 1))[:, 1]
    return c["model"].predict(raw)


def high_mask(fraud_score) -> np.ndarray:
    r = _load()["thresholds"]["high_rule"]
    assert r["op"] == ">" and r["missing"] == "not HIGH"
    fs = pd.to_numeric(pd.Series(fraud_score).astype("object"), errors="coerce").to_numpy(
        dtype="float64"
    )
    return np.nan_to_num(fs, nan=-np.inf) > float(r["value"])


def band_of(raw, fraud_score) -> np.ndarray:
    t = _load()["thresholds"]
    s = np.nan_to_num(np.asarray(raw, dtype="float64"), nan=-np.inf)
    return np.where(
        high_mask(fraud_score), "high", np.where(s >= t["t_low"], "review", "low")
    ).astype(object)


def score(df: pd.DataFrame):
    """Return (prob, band) as numpy arrays aligned with df rows."""
    fs = df["fraud_score"].to_numpy()
    n = len(df)
    oos = (
        df["transaction_status"].isin(OUT_OF_SCOPE_STATUSES).to_numpy()
        if "transaction_status" in df.columns
        else np.zeros(n, bool)
    )
    prob = np.full(n, np.nan)
    band = np.empty(n, dtype=object)
    if (~oos).any():
        sub = df.loc[~oos]
        raw = score_raw(sub)
        prob[~oos] = calibrate(raw)
        band[~oos] = band_of(raw, sub["fraud_score"].to_numpy())
    if oos.any():
        # HIGH rule first, then the Pending/Reversed shortcut
        band[oos] = np.where(high_mask(fs[oos]), "high", "out_of_scope")
    return prob, band


def _selftest() -> None:
    """Score VAL through the app path and check it reproduces the frozen VAL band counts."""
    import sys

    sys.path.insert(0, str(ART.parent))
    from triage.features import load_splits  # VAL only; test is refused by the loader

    va = load_splits(("val",))
    assert set(va["split"]) == {"val"}
    prob, band = score(va.drop(columns=["is_fraud"]))
    t = _load()["thresholds"]
    exp = t["val"]["band_counts"]
    got = {b: int((band == b).sum()) for b in ("high", "review", "low")}
    y = va["is_fraud"].to_numpy()
    assert got == exp, (got, exp)
    assert (
        int((band == "high").sum())
        == int((y & (band == "high")).sum())
        == t["high_rule"]["val"]["tp"]
    )
    assert np.isfinite(prob).all() and ((prob >= 0) & (prob <= 1)).all()
    assert (band[va["fraud_score"].isna().to_numpy()] != "high").all()
    print("selftest OK", got, "fraud in low:", int((y & (band == "low")).sum()))

    # status-order case (synthetic statuses on real val feature rows)
    case = va.drop(columns=["is_fraud"]).iloc[:6].copy()
    case["fraud_score"] = [45.0, 30.0, np.nan, 30.01, 45.0, 10.0]
    case["transaction_status"] = [
        "Pending",
        "Reversed",
        "Pending",
        "Reversed",
        "Approved",
        "Declined",
    ]
    p2, b2 = score(case)
    exp2 = ["high", "out_of_scope", "out_of_scope", "high", "high"]
    assert list(b2[:5]) == exp2, list(b2)
    assert b2[5] in ("review", "low")
    assert np.isnan(p2[:4]).all() and np.isfinite(p2[4:]).all()
    # Pending/Reversed rows need only fraud_score + status
    b3 = score(
        pd.DataFrame({"fraud_score": [31.0, None], "transaction_status": ["Pending", "Reversed"]})
    )[1]
    assert list(b3) == ["high", "out_of_scope"], list(b3)
    print("selftest status-order OK", list(b2))


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        _selftest()
