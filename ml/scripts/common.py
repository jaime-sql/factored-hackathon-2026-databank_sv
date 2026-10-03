import json
import os
import random
import sys

import numpy as np

ROOT = "/workspace/hack-ml"
sys.path.insert(0, ROOT)
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
SEED = 20260929
random.seed(SEED)
np.random.seed(SEED)
os.environ["PYTHONHASHSEED"] = str(SEED)
MLFLOW_URI = f"file:{ROOT}/mlruns"
EXPERIMENT = "fraud-triage"
WORK = f"{ROOT}/work"  # intermediate (val-only) outputs
ART = f"{ROOT}/artifacts"  # frozen deliverables
os.makedirs(WORK, exist_ok=True)
os.makedirs(ART, exist_ok=True)


def dump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o))


V1_TOP_KEYS = (
    "thresholds",
    "bands",
    "fairness",
    "threshold_stability",
    "low_band_tradeoff",
    "high_band_fp_fraud_score",
)


def migrate_v1_keys(R: dict) -> dict:
    """Idempotently move v1 (model-based HIGH, n=350) banding keys of val_results.json under R['superseded_v1']."""
    sv = R.setdefault("superseded_v1", {})
    for k in V1_TOP_KEYS:
        if k in R:
            sv[k] = R.pop(k)
    lg = R.get("compare", {}).get("models", {}).get("lightgbm", {})
    if "at_high_threshold" in lg:
        sv["compare_lightgbm_at_high_threshold"] = lg.pop("at_high_threshold")
    R.pop("bands_v1_superseded_note", None)
    sv["note"] = (
        "v1 banding: HIGH = LightGBM raw score >= 0.0164888 (350 flagged on val). Superseded by banding_v2 "
        "(HIGH = fraud_score > 30). Kept for the record only."
    )
    return R
