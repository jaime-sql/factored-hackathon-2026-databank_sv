"""VALIDATION ONLY: automation vs missed-fraud curve over LightGBM raw-score cuts. Never touches test."""

import datetime
import json
import sys

sys.path.insert(0, "/workspace/hack-ml")
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

from triage.features import LABEL, MANIFEST, load_splits
from triage.score import _load, high_mask

T = 0.000275603870032301
thr = _load()["thresholds"]
assert abs(thr["t_low"] - T) < 1e-18
va = load_splits(("val",))
assert set(va["split"]) == {"val"}
raw = np.load("/workspace/hack-ml/work/val_lgbm_scores.npy")
assert len(raw) == len(va)
y = va[LABEL].to_numpy().astype(bool)
fs = va["fraud_score"].to_numpy(dtype="float64")
hi = high_mask(fs)
c_tr = pa.scalar(datetime.datetime.fromisoformat(MANIFEST["cutoff_train_end"]), pa.timestamp("us"))
c_va = pa.scalar(datetime.datetime.fromisoformat(MANIFEST["cutoff_val_end"]), pa.timestamp("us"))
ts = pc.field("transaction_ts_utc")
pr = (
    ds.dataset("/workspace/hackathon-data/out/gold/transactions_masked.parquet")
    .to_table(
        columns=["is_fraud", "fraud_score"],
        filter=pc.field("transaction_status").isin(["Pending", "Reversed"])
        & (ts >= c_tr)
        & (ts < c_va),
    )
    .to_pandas()
)
pr_fs = pr["fraud_score"].astype("float64").to_numpy()
pr_y = pr["is_fraud"].astype(bool).to_numpy()
pr_hi = np.nan_to_num(pr_fs, nan=-np.inf) > 30

N = len(va) + len(pr)
n_high = int(hi.sum() + pr_hi.sum())
n_rule = int((~pr_hi).sum())
P = int(y.sum() + pr_y.sum())
f_high = int((hi & y).sum() + (pr_hi & pr_y).sum())
f_rule = int((~pr_hi & pr_y).sum())
s = np.nan_to_num(raw[~hi], nan=-np.inf)
ys = y[~hi]
n_model = len(s)
order = np.sort(s)
fraud_sorted = np.sort(s[ys])


def wilson(k, n, z=1.959963984540054):
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (c - h) / d, (c + h) / d


fin = s[np.isfinite(s)]
lo, hi_s = float(fin[fin > 0].min()), float(fin.max())
cuts = sorted(set(np.geomspace(lo, hi_s, 199).tolist()) | {T})
pts = []
for c in cuts:
    n_low = int(np.searchsorted(order, c, side="left"))
    k = int(np.searchsorted(fraud_sorted, c, side="left"))
    n_rev = n_model - n_low
    a, b = wilson(k, P)
    pts.append(
        dict(
            cut=c,
            n_low=n_low,
            n_review=n_rev,
            automation_rate=round((n_rule + n_low) / N, 6),
            missed_fraud=dict(
                k=k, n=P, rate=round(k / P, 6), ci_low=round(a, 6), ci_high=round(b, 6)
            ),
            recall_outside_low=round(1 - k / P, 6),
            fraud_in_low_per_10k_low=(round(1e4 * k / n_low, 4) if n_low else None),
            cost_per_case=None,
            **({"default": True} if c == T else {}),
        )
    )
out = dict(
    version="sim-curve-v1-2026-10-03",
    split="validation",
    generated_at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    model=dict(
        name="LightGBM c5_nl15_mcs1000_spw1 (frozen)",
        score="raw probability (model.txt)",
        model_sha256=thr.get("model_sha256"),
        thresholds_version=thr.get("version"),
    ),
    t_low_default=T,
    n_charges=N,
    n_high=n_high,
    n_rule=n_rule,
    n_fraud_total=P,
    fraud_in_high=f_high,
    fraud_in_rule=f_rule,
    notes=[
        "Validation split only; test never read.",
        "Routing: HIGH = fraud_score > 30 first (any status, fixed); non-HIGH Pending/Reversed -> rule (auto); non-HIGH Approved/Declined -> REVIEW if raw score >= cut else LOW (auto).",
        "automation_rate = (n_rule + n_low) / n_charges; missed_fraud = fraud in LOW / all validation fraud (n=610), Wilson 95% CI.",
        "Pending/Reversed fraud: %d HIGH, %d rule." % (int((pr_hi & pr_y).sum()), f_rule),
        "Cuts: %d log-spaced over the non-HIGH score range plus the exact default t_low (default: true)."
        % (len(cuts) - 1),
        "cost_per_case is null until LLM cost per call is measured.",
    ],
    points=pts,
)
p = "/workspace/hack-ml/work/sim_curve.json"
json.dump(out, open(p, "w"), separators=(",", ":"))
d = [x for x in pts if x.get("default")][0]
print(json.dumps({k: v for k, v in out.items() if k != "points"}, indent=1))
print(json.dumps(d))
print(
    "PR fraud high/rule",
    int((pr_hi & pr_y).sum()),
    f_rule,
    "points",
    len(pts),
    "auto range",
    pts[0]["automation_rate"],
    pts[-1]["automation_rate"],
    "nan scores",
    int(np.isnan(raw[~hi]).sum()),
)
