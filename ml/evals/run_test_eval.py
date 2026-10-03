"""ONE-TIME frozen TEST evaluation (scheduled for Oct 1 2026 by explicit instruction).

DO NOT RUN without explicit go-ahead. Refuses unless ALLOW_TEST_EVAL=1.
Verifies the TEST key hash against splits_manifest.json before scoring anything, then evaluates the
frozen artifacts (no refitting, no threshold changes): rule vs LR vs LightGBM (same metrics as VAL,
bootstrap CIs), v2 bands (HIGH = fraud_score > 30 rule; REVIEW/LOW by LightGBM raw score vs frozen
t_low; 90% t_low as sensitivity only), Pending/Reversed HIGH-rule line, and fairness. Writes docs/evaluation_test.md and
artifacts/test_results.json, logs an MLflow run. Refuses to run twice unless ALLOW_TEST_RERUN=1.
    ALLOW_TEST_EVAL=1 .venv/bin/python evals/run_test_eval.py
"""

import os
import sys

if os.environ.get("ALLOW_TEST_EVAL") != "1":
    sys.exit(
        "REFUSED: TEST split is frozen. Set ALLOW_TEST_EVAL=1 only for the single sanctioned run."
    )

ROOT = "/workspace/hack-ml"
sys.path.insert(0, ROOT)
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
OUT_JSON = f"{ROOT}/artifacts/test_results.json"
OUT_JSON_WORK = f"{ROOT}/work/test_results.json"
for _p in (OUT_JSON, OUT_JSON_WORK):
    if os.path.exists(_p) and os.environ.get("ALLOW_TEST_RERUN") != "1":
        sys.exit(f"REFUSED: {_p} exists; the test eval has already been run once.")
# claim the single run BEFORE any test data is read, so a crash mid-run still blocks a silent second run
import datetime as _dt

with open(f"{ROOT}/work/TEST_EVAL_STARTED", "x") as _m:
    _m.write(_dt.datetime.now().astimezone().isoformat(timespec="seconds") + "\n")

import hashlib
import json
import time

import joblib
import mlflow
import numpy as np
import pyarrow.compute as pc
import pyarrow.dataset as ds

from triage.features import (
    FEATURES_PATH,
    LABEL,
    MANIFEST,
    NUM,
    RULE_SCORE,
    SLICES,
    load_splits,
    rule_flag,
    sorted_key_hash,
)
from triage.metrics import reliability
from triage.report import compare, fairness, fairness_markdown
from triage.score import band_of, calibrate, high_mask, score_raw
from triage.thresholds import band_report

t0 = time.time()
ART = f"{ROOT}/artifacts"
thr = json.load(open(f"{ART}/thresholds.json"))
model_sha = hashlib.sha256(open(f"{ART}/model.txt", "rb").read()).hexdigest()
assert model_sha == thr["model_sha256"], "model.txt changed since freeze"
assert thr.get("version", "").startswith("v2") and "high_rule" in thr, (
    "expected v2 banding thresholds.json"
)

# 1) verify TEST hash BEFORE loading any features/labels
keys = ds.dataset(FEATURES_PATH).to_table(
    columns=["transaction_key"], filter=pc.field("split") == "test"
)
h = sorted_key_hash(keys["transaction_key"].to_pylist())
expected = MANIFEST["splits"]["test"]["sha256_sorted_ids"]
if h != expected:
    sys.exit(f"ABORT: test hash mismatch {h} != manifest {expected}")
print("test hash OK", h, keys.num_rows)

# 2) load & score (frozen)
te = load_splits(("test",), _allow_test=True)
y = te[LABEL].to_numpy()
raw = score_raw(te)
prob = calibrate(raw)
fs_raw = te[RULE_SCORE].to_numpy()
band = np.asarray(band_of(raw, fs_raw)).astype(str)  # v2 banding, identical to triage.score.score
hi = high_mask(fs_raw)
t90 = thr["selection"]["sensitivity_90"]["t_low"]
band90 = np.where(hi, "high", np.where(np.nan_to_num(raw, nan=-np.inf) >= t90, "review", "low"))
lr = joblib.load(f"{ART}/logreg_baseline.joblib")
p_lr = lr.predict_proba(te[NUM].to_numpy(dtype="float64"))[:, 1]
fs = te[RULE_SCORE].to_numpy(dtype="float64")
rf = rule_flag(te)

cmp = compare({"rule_fraud_score": fs, "logreg": p_lr, "lightgbm": raw}, y, rf, n_boot=1000)
bands = band_report(band, y)
bands90 = band_report(band90, y)
Nl = int((~y).sum())
high_op = dict(
    flagged=int(hi.sum()),
    tp=int((hi & y).sum()),
    fp=int((hi & ~y).sum()),
    precision=float(y[hi].mean()) if hi.any() else None,
    recall=float((hi & y).sum() / y.sum()),
    fpr=float((hi & ~y).sum() / Nl),
    wrongful_flags_per_10k_legit=float(1e4 * (hi & ~y).sum() / Nl),
)
fair = fairness(te[SLICES], y, band, SLICES)
calib = reliability(prob, y)
# Pending/Reversed (outside gold fraud_features): HIGH rule runs before the Pending/Reversed shortcut.
# Same line as VAL (scripts/05_pending_reversed_high.py), from gold.transactions_masked, TEST window only.
from datetime import datetime

import pyarrow as pa

from triage.thresholds import high_rule_mask

_c_va = pa.scalar(datetime.fromisoformat(MANIFEST["cutoff_val_end"]), pa.timestamp("us"))
_pr = (
    ds.dataset("/workspace/hackathon-data/out/gold/transactions_masked.parquet")
    .to_table(
        columns=["transaction_ts_utc", "transaction_status", "is_fraud", "fraud_score"],
        filter=pc.field("transaction_status").isin(["Pending", "Reversed"])
        & (pc.field("transaction_ts_utc") >= _c_va),
    )
    .to_pandas()
)
_pr_fs = _pr["fraud_score"].astype("float64").to_numpy()
_pr["high"] = high_rule_mask(_pr_fs)
_pr["fs_null"] = np.isnan(_pr_fs)
pending_reversed_high = {}
for _s in ("Pending", "Reversed", "Pending+Reversed"):
    _x = _pr[
        _pr["transaction_status"].isin(
            ["Pending", "Reversed"] if _s == "Pending+Reversed" else [_s]
        )
    ]
    _y = _x["is_fraud"].astype(bool)
    pending_reversed_high[_s] = dict(
        rows=int(len(_x)),
        fraud=int(_y.sum()),
        fraud_caught_high=int((_x["high"] & _y).sum()),
        legit_flagged_high=int((_x["high"] & ~_y).sum()),
        missing_fraud_score=int(_x["fs_null"].sum()),
    )
res = dict(
    pending_reversed_high=pending_reversed_high,
    test_sha256=h,
    rows=len(te),
    positives=int(y.sum()),
    model_sha256=model_sha,
    thresholds=thr,
    compare=cmp,
    high_rule_operating_point=high_op,
    bands=bands,
    sensitivity_low_90_bands=bands90,
    fairness=fair,
    calibration_test=calib,
)

# ---- extensions added 2026-10-03 before the single run (no tuning; all thresholds frozen) ----
from triage.metrics import Ranked as _R
from triage.metrics import recall_at_fpr as _rafpr


def _wilson(k, n, z=1.959963984540054):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return [float((c - h) / d), float((c + h) / d)]


ext = {}
# (a) PR-AUC point estimates + CIs
ext["pr_auc"] = {
    k: dict(point=v["pr_auc"], ci95=ci_ if (ci_ := cmp["bootstrap_95ci"][k]["pr_auc"]) else None)
    for k, v in cmp["models"].items()
}
# (b) recall at 0.02% FPR (fraud_score used as a continuous score for the rule)
ext["recall_at_fpr_0p0002"] = {}
for k, sc in {"rule_fraud_score": fs, "lightgbm": raw, "logreg": p_lr}.items():
    _tp, _fp = _R(sc, y).curve()
    rec, i = _rafpr(_tp, _fp, 0.0002)
    ext["recall_at_fpr_0p0002"][k] = dict(
        recall=rec, tp=int(_tp[i]) if i >= 0 else 0, fp=int(_fp[i]) if i >= 0 else 0
    )
# (e) paired bootstrap PR-AUC(model) - PR-AUC(rule)
_b = cmp["bootstrap_95ci"]
ext["pr_auc_diff_lightgbm_minus_rule"] = dict(
    point=cmp["models"]["lightgbm"]["pr_auc"] - cmp["models"]["rule_fraud_score"]["pr_auc"],
    ci95_paired=_b["lightgbm"]["diff_pr_auc_vs_rule_fraud_score_ci"],
    n_boot=cmp["bootstrap_n"],
    seed=20260929,
    resampling="row-level, Approved/Declined test rows",
)
ext["pr_auc_diff_logreg_minus_rule"] = dict(
    point=cmp["models"]["logreg"]["pr_auc"] - cmp["models"]["rule_fraud_score"]["pr_auc"],
    ci95_paired=_b["logreg"]["diff_pr_auc_vs_rule_fraud_score_ci"],
)
# routing over ALL test-window charges: HIGH (any status) -> Pending/Reversed rule -> REVIEW/LOW
_prh = _pr["high"].to_numpy()
_pry = _pr["is_fraud"].astype(bool).to_numpy()
n_ad = len(y)
n_pr = len(_pr)
n_all = n_ad + n_pr
n_high = int(hi.sum() + _prh.sum())
n_rule = int((~_prh).sum())
n_low = int((band == "low").sum())
n_review = int((band == "review").sum())
P_ad = int(y.sum())
P_pr = int(_pry.sum())
P_all = P_ad + P_pr
f_low = int(((band == "low") & y).sum())
f_review = int(((band == "review") & y).sum())
f_high = int((hi & y).sum() + (_prh & _pry).sum())
f_rule = int((~_prh & _pry).sum())
legit_high_all = int((hi & ~y).sum() + (_prh & ~_pry).sum())
# (c) wrongful blocks
ext["wrongful_blocks"] = dict(
    legit_in_high_AD=int((hi & ~y).sum()),
    legit_in_high_PR=int((_prh & ~_pry).sum()),
    per_10k_charges_all=1e4 * legit_high_all / n_all,
    per_10k_charges_AD=1e4 * int((hi & ~y).sum()) / n_ad,
    per_10k_legit_AD=high_op["wrongful_flags_per_10k_legit"],
)
# (d) threshold transfer: recall at validation t_low vs 95% target
ext["threshold_transfer"] = dict(
    t_low=thr["t_low"],
    target_recall=0.95,
    recall_outside_low_AD=1 - f_low / P_ad,
    fraud_in_low_AD=f_low,
    fraud_AD=P_ad,
    recall_outside_low_all=1 - f_low / P_all,
    missed_fraud=dict(
        k=f_low,
        n=P_all,
        share=f_low / P_all,
        wilson95=_wilson(f_low, P_all),
        denominator="all test-window fraud (Approved/Declined + Pending/Reversed), as locked on VAL (29/610)",
    ),
    fraud_in_high=f_high,
    fraud_in_rule=f_rule,
    fraud_in_review=f_review,
    fraud_in_low=f_low,
    fraud_total=P_all,
    meets_target=bool(1 - f_low / P_all >= 0.95),
)
# (f) routing-order split
ext["routing_split"] = dict(
    n_charges=n_all,
    n_approved_declined=n_ad,
    n_pending_reversed=n_pr,
    n_high=n_high,
    n_high_from_AD=int(hi.sum()),
    n_high_from_PR=int(_prh.sum()),
    n_rule=n_rule,
    n_review=n_review,
    n_low=n_low,
    low_share_all=n_low / n_all,
    low_share_AD=n_low / n_ad,
    automation_rate=(n_rule + n_low) / n_all,
    human_share=(n_high + n_review) / n_all,
    automation_definition="(Pending/Reversed rule + LOW) / all test-window charges; HIGH and REVIEW go to a human",
)
res["extensions"] = ext
print(json.dumps(ext, indent=1, default=str))
with open(OUT_JSON, "w") as f:
    json.dump(res, f, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o))
import shutil

shutil.copyfile(OUT_JSON, OUT_JSON_WORK)

mlflow.set_tracking_uri(f"file:{ROOT}/mlruns")
mlflow.set_experiment("fraud-triage")
with mlflow.start_run(run_name="TEST_EVAL_single_run") as run:
    mlflow.log_params(
        dict(
            test_sha256=h,
            model_sha256=model_sha,
            banding=thr["version"],
            high_rule=thr["high_rule"]["expr"],
            t_low=thr["t_low"],
            val_final_run_id=thr["mlflow_final_run_id"],
        )
    )
    for k, v in cmp["models"].items():
        mlflow.log_metrics(
            {
                f"test_{k}_pr_auc": v["pr_auc"],
                f"test_{k}_roc_auc": v["roc_auc"],
                f"test_{k}_recall_at_rule_fpr": v["recall_at_rule_fpr"],
                f"test_{k}_precision_at_rule_recall": v["precision_at_rule_recall"],
            }
        )
    for b in ("low", "review", "high"):
        mlflow.log_metrics(
            {
                f"test_band_{b}_share": bands[b]["share"],
                f"test_band_{b}_fraud_rate": bands[b]["fraud_rate"] or 0.0,
            }
        )
    mlflow.log_metric("test_false_auto_close_per_10k", bands["false_auto_close_per_10k_tx"])
    mlflow.log_metrics({f"test_high_{k}": float(v) for k, v in high_op.items() if v is not None})
    mlflow.log_metrics(
        {
            f"test_pr_{_s.replace('+', '_')}_{k}": float(v)
            for _s, _d in pending_reversed_high.items()
            for k, v in _d.items()
        }
    )
    mlflow.log_metric("test_brier_calibrated", calib["brier"])
    mlflow.log_artifact(OUT_JSON)
    run_id = run.info.run_id

ci = cmp["bootstrap_95ci"]
r = cmp["rule_operating_point"]
L = [
    "# TEST evaluation (single frozen run)\n",
    f"- test sha256: `{h}` (matches manifest), rows {len(te):,}, positives {int(y.sum())}",
    f"- model sha256 `{model_sha}`; banding {thr['version']}: HIGH = `{thr['high_rule']['expr']}` (missing -> not HIGH), t_low={thr['t_low']:.6g} (raw score); MLflow run `{run_id}`\n",
    f"Rule fraud_score>=30: flagged {r['flagged']}, TP {r['tp']}, precision {r['precision']:.4f}, recall {r['recall']:.4f}, FPR {r['fpr']:.6f} ({r['wrongful_flags_per_10k_legit']:.2f}/10k legit)\n",
    "| model | PR-AUC [95% CI] | ROC-AUC | recall @ rule FPR [95% CI] | precision @ rule recall | wrongful flags/10k @ rule FPR |",
    "|---|---|---|---|---|---|",
]
for k, v in cmp["models"].items():
    a = v["at_rule_fpr"]
    L.append(
        f"| {k} | {v['pr_auc']:.4f} [{ci[k]['pr_auc'][0]:.4f}, {ci[k]['pr_auc'][1]:.4f}] | {v['roc_auc']:.4f} | "
        f"{v['recall_at_rule_fpr']:.4f} [{ci[k]['recall_at_rule_fpr'][0]:.4f}, {ci[k]['recall_at_rule_fpr'][1]:.4f}] | "
        f"{v['precision_at_rule_recall']:.4f} | {a['wrongful_flags_per_10k_legit'] if a else float('nan'):.2f} |"
    )
hv = high_op
L.append(
    f"\nHIGH rule (fraud_score > 30): flagged {hv['flagged']}, TP {hv['tp']}, FP {hv['fp']}, precision {hv['precision'] if hv['precision'] is not None else float('nan'):.4f}, recall {hv['recall']:.4f}, FPR {hv['fpr']:.6f} ({hv['wrongful_flags_per_10k_legit']:.2f}/10k legit)\n"
)
L.append(
    "| band | n | share | fraud | fraud rate | share of all fraud | share of legit |\n|---|---|---|---|---|---|---|"
)
for b in ("low", "review", "high"):
    d = bands[b]
    L.append(
        f"| {b} | {d['n']:,} | {d['share'] * 100:.3f}% | {d['fraud']} | {(d['fraud_rate'] or 0) * 100:.4f}% | {d['share_of_all_fraud'] * 100:.2f}% | {d['share_of_legit'] * 100:.2f}% |"
    )
L.append(
    f"\nFalse auto-close (fraud in LOW) per 10k transactions: {bands['false_auto_close_per_10k_tx']:.3f}\n"
)
L.append(
    f"Sensitivity only (90% t_low={t90:.6g}): LOW share {bands90['low']['share'] * 100:.2f}%, fraud in LOW {bands90['low']['fraud']}, false auto-close/10k {bands90['false_auto_close_per_10k_tx']:.3f}\n"
)
L.append("## Pending / Reversed (HIGH rule runs before the shortcut)\n")
L.append(
    "| status | rows | fraud | fraud caught by fraud_score > 30 | legit wrongly flagged | missing fraud_score |\n|---|---|---|---|---|---|"
)
for _s, _d in pending_reversed_high.items():
    L.append(
        f"| {_s} | {_d['rows']:,} | {_d['fraud']} | {_d['fraud_caught_high']} | {_d['legit_flagged_high']} | {_d['missing_fraud_score']:,} |"
    )
L.append("")
L.append("## Fairness\n" + fairness_markdown(fair))
L.append(
    "\nFlags (FPR ratio outside 0.8-1.25):\n"
    + ("\n".join(f"- {f}" for f in fair["flags"]) or "- none")
)
open(f"{ROOT}/docs/evaluation_test.md", "w").write("\n".join(L) + "\n")
print("done", run_id, f"{time.time() - t0:.0f}s")
