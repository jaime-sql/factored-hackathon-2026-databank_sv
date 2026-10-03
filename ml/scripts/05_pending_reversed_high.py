"""Stage 5: (a) move v1 banding keys of val_results.json under superseded_v1; (b) measure the HIGH rule
(fraud_score > 30) on Pending/Reversed charges in the TRAIN and VAL windows (labels), and count TEST-window
rows only (no labels, no scores). Source: gold.transactions_masked (1:1 masked copy of silver.transactions;
silver itself lives only in the DE's local duckdb and has raw ids)."""

from datetime import datetime

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
from common import *

from triage.features import MANIFEST
from triage.thresholds import high_rule_mask

SRC = "/workspace/hackathon-data/out/gold/transactions_masked.parquet"
STATUSES = ["Pending", "Reversed"]
c_tr = datetime.fromisoformat(MANIFEST["cutoff_train_end"])
c_va = datetime.fromisoformat(MANIFEST["cutoff_val_end"])
d = ds.dataset(SRC)
ts, st = pc.field("transaction_ts_utc"), pc.field("transaction_status")
in_scope = st.isin(STATUSES)

# TRAIN + VAL windows only (labels allowed)
tb = d.to_table(
    columns=["transaction_ts_utc", "transaction_status", "is_fraud", "fraud_score"],
    filter=in_scope & (ts < pa.scalar(c_va, pa.timestamp("us"))),
)
df = tb.to_pandas()
assert df["transaction_ts_utc"].max() < c_va
df["window"] = np.where(df["transaction_ts_utc"] < c_tr, "train", "val")
fs = df["fraud_score"].astype("float64").to_numpy()
df["high"] = high_rule_mask(fs)
df["fs_null"] = np.isnan(fs)
df["fs_eq30"] = fs == 30.0
res = {}
for w in ("train", "val"):
    res[w] = {}
    for s in STATUSES + ["Pending+Reversed"]:
        m = (df["window"] == w) & (
            df["transaction_status"].isin(STATUSES if s == "Pending+Reversed" else [s])
        )
        x = df[m]
        y = x["is_fraud"].astype(bool)
        res[w][s] = dict(
            rows=int(len(x)),
            fraud=int(y.sum()),
            fraud_caught_high=int((x["high"] & y).sum()),
            legit_flagged_high=int((x["high"] & ~y).sum()),
            missing_fraud_score=int(x["fs_null"].sum()),
            fraud_missing_fraud_score=int((x["fs_null"] & y).sum()),
            legit_at_exactly_30=int((x["fs_eq30"] & ~y).sum()),
            high_rows=int(x["high"].sum()),
        )
# TEST window: row counts only (status column only; no labels, no fraud_score)
tt = d.to_table(
    columns=["transaction_status"], filter=in_scope & (ts >= pa.scalar(c_va, pa.timestamp("us")))
)
test_counts = {s: int(pc.sum(pc.equal(tt["transaction_status"], s)).as_py() or 0) for s in STATUSES}
total_counts = {
    s: int(
        pc.sum(
            pc.equal(
                d.to_table(columns=["transaction_status"], filter=st == s)["transaction_status"], s
            )
        ).as_py()
    )
    for s in STATUSES
}
tv = {s: res["train"][s]["fraud"] + res["val"][s]["fraud"] for s in STATUSES}
analytics = {"Pending": 79, "Reversed": 36, "total": 115}
recon = dict(
    analytics_full_data_fraud=analytics,
    train_plus_val_fraud_observed=tv | {"total": sum(tv.values())},
    implied_test_window_remainder_per_analytics={s: analytics[s] - tv[s] for s in STATUSES}
    | {"total": analytics["total"] - sum(tv.values())},
    note="Remainder = analytics figure minus observed train+val counts; test-window labels were NOT read, so it is not verified here.",
    rows_by_window={
        s: dict(
            train=res["train"][s]["rows"],
            val=res["val"][s]["rows"],
            test=test_counts[s],
            sum=res["train"][s]["rows"] + res["val"][s]["rows"] + test_counts[s],
            all_rows_count=total_counts[s],
        )
        for s in STATUSES
    },
)
out = dict(
    source=SRC,
    source_note="gold.transactions_masked = masked 1:1 copy of silver.transactions (4,425,008 rows); rows with transaction_status in Pending/Reversed",
    rule="fraud_score > 30 (missing -> not HIGH); runs before the Pending/Reversed shortcut",
    windows=dict(
        train=f"ts_utc < {c_tr}",
        val=f"{c_tr} <= ts_utc < {c_va} (CST: < 2026-01-06 18:26:41)",
        test=f"ts_utc >= {c_va}",
    ),
    train=res["train"],
    val=res["val"],
    test_window_rows_only=test_counts,
    reconciliation=recon,
)
print(json.dumps(out, indent=1))

R = json.load(open(f"{ART}/val_results.json"))
migrate_v1_keys(R)
R["pending_reversed_high"] = out
dump(R, f"{ART}/val_results.json")
T = json.load(open(f"{ART}/thresholds.json"))
T["status_rule"] = dict(
    order=[
        "high_rule (fraud_score > 30)",
        "Pending/Reversed shortcut -> out_of_scope",
        "model REVIEW/LOW",
    ],
    out_of_scope_statuses=STATUSES,
    decided="2026-09-29 team decision",
    pending_reversed_val=out["val"]["Pending+Reversed"],
)
dump(T, f"{ART}/thresholds.json")
print("top-level keys:", list(R))
