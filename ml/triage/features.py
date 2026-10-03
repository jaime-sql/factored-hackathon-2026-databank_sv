"""Feature definitions, data loading and preprocessing for the fraud triage model.

Only the manifest's feature lists are used. Slice columns are loaded separately for
fairness reporting and are never passed to a model.
"""

from __future__ import annotations

import hashlib
import json
import os

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

DATA_DIR = "/workspace/hackathon-data"
FEATURES_PATH = f"{DATA_DIR}/out/gold/fraud_features.parquet"
MANIFEST_PATH = f"{DATA_DIR}/splits_manifest.json"

with open(MANIFEST_PATH) as _f:
    MANIFEST = json.load(_f)

NUM = list(MANIFEST["features_numeric"])
CAT = list(MANIFEST["features_categorical"])
SLICES = list(MANIFEST["slice_columns_not_features"])
LABEL = MANIFEST["label"]  # is_fraud
RULE_SCORE = "fraud_score"
RULE_THRESHOLD = 30.0


def sorted_key_hash(keys) -> str:
    """sha256 over sorted transaction_key joined by \\n with trailing \\n (manifest definition)."""
    k = sorted(map(str, keys))
    return hashlib.sha256(("\n".join(k) + "\n").encode()).hexdigest()


def _to_pandas(tb: pa.Table) -> pd.DataFrame:
    # cast decimals to float64 in arrow (avoids python Decimal objects in pandas)
    cols = []
    for f in tb.schema:
        col = tb[f.name]
        if pa.types.is_decimal(f.type):
            col = pc.cast(col, pa.float64())
        cols.append(col)
    tb = pa.Table.from_arrays(cols, names=tb.schema.names)
    df = tb.to_pandas()
    for c in df.columns:
        if c in NUM or c == RULE_SCORE:
            df[c] = df[c].astype("float32")
    return df


def load_splits(splits=("train", "val"), extra_cols=(), _allow_test: bool = False) -> pd.DataFrame:
    """Load the requested splits. Test rows are filtered at scan time and never loaded
    unless _allow_test=True AND env ALLOW_TEST_EVAL=1 (only the frozen test-eval script does that)."""
    splits = tuple(splits)
    if "test" in splits:
        if not (_allow_test and os.environ.get("ALLOW_TEST_EVAL") == "1"):
            raise PermissionError(
                "TEST split is frozen. Set ALLOW_TEST_EVAL=1 in run_test_eval.py only."
            )
    cols = (
        ["transaction_key", "transaction_ts_utc", "split", LABEL]
        + NUM
        + CAT
        + SLICES
        + list(extra_cols)
    )
    cols = list(dict.fromkeys(cols))
    d = ds.dataset(FEATURES_PATH)
    flt = pc.field("split").isin(list(splits))
    if "test" not in splits:
        flt = flt & (pc.field("split") != "test")
    df = _to_pandas(d.to_table(columns=cols, filter=flt))
    assert set(df["split"].unique()) <= set(splits)
    df[LABEL] = df[LABEL].astype(bool)
    return df


def build_cat_maps(train_df: pd.DataFrame) -> dict:
    """Category vocabularies from TRAIN only (sorted, for determinism). Unseen/missing -> NaN."""
    return {c: sorted(train_df[c].dropna().astype(str).unique().tolist()) for c in CAT}


def prepare(df: pd.DataFrame, cat_maps: dict, features: list[str] | None = None) -> pd.DataFrame:
    """Model matrix: float32 numerics + pandas Categorical with fixed train vocabularies."""
    features = features or (NUM + CAT)
    out = {}
    for c in features:
        if c in CAT:
            s = df[c].astype("object").where(df[c].notna(), None)
            out[c] = pd.Categorical(s, categories=cat_maps[c])
        else:
            out[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
    return pd.DataFrame(out, index=df.index)


def rule_flag(df: pd.DataFrame) -> np.ndarray:
    """Baseline: coalesce(fraud_score >= 30, false)."""
    s = pd.to_numeric(df[RULE_SCORE], errors="coerce").to_numpy(dtype="float64")
    return np.nan_to_num(s, nan=-np.inf) >= RULE_THRESHOLD
