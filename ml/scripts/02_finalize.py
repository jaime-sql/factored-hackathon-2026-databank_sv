"""Stage 2: select model, reproducibility check, VAL comparison + bootstrap, calibration (time
cross-fitting within VAL), thresholds, fairness, importance/leakage checks, freeze artifacts.
TRAIN/VAL only; TEST is never loaded."""

import copy
import hashlib
import shutil
import time

import joblib
import lightgbm as lgb
import mlflow
import pandas as pd
from common import *
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from triage.features import *
from triage.metrics import Ranked, average_precision, reliability, roc_auc
from triage.report import compare, fairness, fairness_markdown
from triage.thresholds import assign_band, band_report, low_band_tradeoff, select_thresholds

mlflow.set_tracking_uri(MLFLOW_URI)
mlflow.set_experiment(EXPERIMENT)
t0 = time.time()
search = json.load(open(f"{WORK}/lgbm_search.json"))
cands = [r for r in search if not r["ablation"]]
top = max(cands, key=lambda r: r["pr_auc"])
# Selection rule (documented): primary = VAL PR-AUC. Candidates within TIE_TOL of the top PR-AUC
# (far inside the bootstrap CI width) are treated as tied; among ties prefer native categorical
# handling (no extra encoders to ship), then fewer leaves, then larger min_child_samples (simpler model).
TIE_TOL = 0.001
tied = [r for r in cands if r["pr_auc"] >= top["pr_auc"] - TIE_TOL]
best = sorted(
    tied,
    key=lambda r: (
        r["cfg"]["cat"] != "native",
        r["params"]["num_leaves"],
        -r["params"]["min_child_samples"],
        -r["pr_auc"],
    ),
)[0]
selection = dict(
    top_by_pr_auc=top["name"],
    top_pr_auc=top["pr_auc"],
    tie_tol=TIE_TOL,
    tied=[r["name"] for r in tied],
    selected=best["name"],
)
print("selection", selection)
ablation = [r for r in search if r["ablation"]]
lrs = json.load(open(f"{WORK}/lr.json"))
lr_best = max(lrs, key=lambda r: r["pr_auc"])
rule_info = json.load(open(f"{WORK}/rule.json"))
hashes = json.load(open(f"{WORK}/hashes.json"))
cat_maps = json.load(open(f"{WORK}/cat_maps.json"))
print("best:", best["name"], best["pr_auc"], "LR:", lr_best["class_weight"], lr_best["pr_auc"])

df = load_splits(("train", "val"))
tr = df[df.split == "train"].reset_index(drop=True)
va = df[df.split == "val"].reset_index(drop=True)
del df
va = va.sort_values(["transaction_ts_utc", "transaction_key"], kind="stable").reset_index(drop=True)
ytr, yva = tr[LABEL].to_numpy(), va[LABEL].to_numpy()
feats = best["features"]
assert best["cfg"]["cat"] == "native", "freeze path below assumes native categorical handling"
Xtr, Xva = prepare(tr, cat_maps, feats), prepare(va, cat_maps, feats)

# ---- reproducibility: retrain best config from scratch, same seed -> identical predictions?
params = copy.deepcopy(best["params"])
params.pop("metric", None)
params.pop("first_metric_only", None)
params["metric"] = "None"
bst2 = lgb.train(params, lgb.Dataset(Xtr, ytr), num_boost_round=best["best_iteration"])
bst = lgb.Booster(model_file=best["model_path"])
p_raw = bst.predict(Xva)
p_re = bst2.predict(Xva)
repro_maxdiff = float(np.max(np.abs(p_raw - p_re)))
print("repro max abs diff", repro_maxdiff)

# ---- scores
lr_model = joblib.load(lr_best["path"])
p_lr = lr_model.predict_proba(va[NUM].to_numpy(dtype="float64"))[:, 1]
fs = va[RULE_SCORE].to_numpy(dtype="float64")
rf = rule_flag(va)


# ---- calibration: 5 contiguous time folds within VAL, cross-fitted (fit on 4, predict held-out)
def logit(p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def fit_platt(p, y):
    m = LogisticRegression(C=1e6, max_iter=1000)
    m.fit(logit(p).reshape(-1, 1), y)
    return m


def fit_iso(p, y):
    m = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    m.fit(p, y.astype(float))
    return m


def apply(m, p):
    return (
        m.predict_proba(logit(p).reshape(-1, 1))[:, 1]
        if isinstance(m, LogisticRegression)
        else m.predict(p)
    )


K = 5
folds = np.array_split(np.arange(len(va)), K)
oof = {"platt": np.zeros(len(va)), "isotonic": np.zeros(len(va))}
for idx in folds:
    trn = np.setdiff1d(np.arange(len(va)), idx)
    oof["platt"][idx] = apply(fit_platt(p_raw[trn], yva[trn]), p_raw[idx])
    oof["isotonic"][idx] = apply(fit_iso(p_raw[trn], yva[trn]), p_raw[idx])


def logloss(p, y):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


calib = {
    "scheme": f"{K} contiguous time folds within VAL; each fold calibrated by a calibrator fit on the other {K - 1} folds (out-of-fold); final calibrator refit on all VAL",
    "raw": reliability(p_raw, yva) | {"logloss": logloss(p_raw, yva)},
}
for k, v in oof.items():
    calib[f"{k}_oof"] = reliability(v, yva) | {"logloss": logloss(v, yva)}
chosen = min(("platt", "isotonic"), key=lambda k: calib[f"{k}_oof"]["brier"])
need = calib[f"{chosen}_oof"]["brier"] < calib["raw"]["brier"]
calib["chosen"] = chosen if need else "none"
calibrator = (fit_platt if chosen == "platt" else fit_iso)(p_raw, yva) if need else None
print(
    "calibration raw brier",
    calib["raw"]["brier"],
    {k: calib[f"{k}_oof"]["brier"] for k in oof},
    "->",
    calib["chosen"],
)

# ---- thresholds (raw model score; calibration is monotone so ranking/bands are unaffected)
prec_target = rule_info["precision"]
thr = select_thresholds(
    p_raw, yva, precision_target=prec_target, low_recall_target=0.95, min_high_flags=50
)
band = assign_band(p_raw, thr["t_low"], thr["t_high"])
bands = band_report(band, yva)
tradeoff = low_band_tradeoff(p_raw, yva)
hi_m = band == "high"
high_fp_fraud_score = va.loc[hi_m & ~yva, RULE_SCORE].describe().to_dict()
high_fp_fraud_score["values"] = (
    va.loc[hi_m & ~yva, RULE_SCORE].value_counts(dropna=False).head(5).to_dict()
)
print("tradeoff", tradeoff)
print("HIGH FP fraud_score", high_fp_fraud_score)
# stability: same procedure on each time-half of VAL
halves = {}
for name, idx in (
    ("first_half", np.arange(len(va) // 2)),
    ("second_half", np.arange(len(va) // 2, len(va))),
):
    th = select_thresholds(p_raw[idx], yva[idx], precision_target=prec_target)
    halves[name] = dict(
        t_high=th["t_high"],
        t_low=th["t_low"],
        high_val=th["high_val"],
        low_val=th["low_val"],
        positives=int(yva[idx].sum()),
    )
    # apply full-VAL thresholds to each half
    b = assign_band(p_raw[idx], thr["t_low"], thr["t_high"])
    halves[name]["full_thresholds_applied"] = band_report(b, yva[idx]) | {
        "high_precision": float(yva[idx][b == "high"].mean()),
        "high_recall": float((yva[idx] & (b == "high")).sum() / yva[idx].sum()),
    }


def cal(x):
    return float(apply(calibrator, np.array([x]))[0]) if calibrator is not None else float(x)


thr["t_high_calibrated_prob"] = cal(thr["t_high"])
thr["t_low_calibrated_prob"] = cal(thr["t_low"])
print("thresholds", {k: v for k, v in thr.items() if k != "notes"}, thr["notes"])
print("bands", bands)

# ---- VAL comparison (rule vs LR vs LightGBM) + bootstrap
cmp = compare(
    {"rule_fraud_score": fs, "logreg": p_lr, "lightgbm": p_raw},
    yva,
    rf,
    n_boot=1000,
    high_thresholds={"lightgbm": thr["t_high"]},
)
if ablation:
    ab = ablation[0]
    Xab = prepare(va, cat_maps, ab["features"])
    p_ab = lgb.Booster(model_file=ab["model_path"]).predict(Xab)
    cmp_ab = compare({"rule_fraud_score": fs, "lgbm_no_fraud_score": p_ab}, yva, rf, n_boot=0)
    cmp["ablation_no_fraud_score"] = cmp_ab["models"]["lgbm_no_fraud_score"]
print(
    json.dumps(
        {
            k: {
                m: v[m]
                for m in ("pr_auc", "roc_auc", "recall_at_rule_fpr", "precision_at_rule_recall")
            }
            for k, v in cmp["models"].items()
        },
        indent=1,
    )
)
print(json.dumps(cmp["bootstrap_95ci"], indent=1))

# ---- fairness
fair = fairness(va[SLICES], yva, band, SLICES)
print("fairness flags", fair["flags"])

# ---- importance + leakage check
gain = bst.feature_importance("gain")
split = bst.feature_importance("split")
imp = pd.DataFrame({"feature": bst.feature_name(), "gain": gain, "split": split})
imp["gain_share"] = imp.gain / imp.gain.sum()
imp = imp.sort_values("gain", ascending=False).reset_index(drop=True)
leak = []
for c in NUM:
    for nm, d, y in (("train", tr, ytr), ("val", va, yva)):
        pass
    s_va = va[c].to_numpy(dtype="float64")
    s_tr = tr[c].to_numpy(dtype="float64")
    tp, fp = Ranked(s_va, yva).curve()
    a = roc_auc(tp, fp)
    tp2, fp2 = Ranked(-np.nan_to_num(s_va, nan=np.inf), yva).curve()
    leak.append(
        dict(
            feature=c,
            val_auc_oriented=max(a, roc_auc(tp2, fp2)),
            val_ap=max(average_precision(tp, fp), average_precision(tp2, fp2)),
            null_rate_val=float(np.isnan(s_va).mean()),
        )
    )
for c in CAT:
    rate = tr.groupby(tr[c].astype("object").fillna("__NA__"))[LABEL].mean()
    enc = va[c].astype("object").fillna("__NA__").map(rate).to_numpy(dtype="float64")
    tp, fp = Ranked(enc, yva).curve()
    leak.append(
        dict(
            feature=c,
            val_auc_oriented=roc_auc(tp, fp),
            val_ap=average_precision(tp, fp),
            null_rate_val=float(va[c].isna().mean()),
        )
    )
leak = sorted(leak, key=lambda d: -d["val_auc_oriented"])
fs_tr = tr[RULE_SCORE].to_numpy(dtype="float64")
fs_facts = {}
for nm, s, y in (("train", fs_tr, ytr), ("val", fs, yva)):
    fs_facts[nm] = {
        f">={t}": dict(n=int((s >= t).sum()), fraud=int(((s >= t) & y).sum())) for t in (30, 40, 50)
    }
    fs_facts[nm]["null_n"] = int(np.isnan(s).sum())
    fs_facts[nm]["null_fraud"] = int((np.isnan(s) & y).sum())
    fs_facts[nm]["<30_fraud"] = int(((s < 30) & y).sum())
print(imp.head(15))
print(leak[:5])
print(fs_facts)

# ---- freeze
shutil.copy(best["model_path"], f"{ART}/model.txt")
joblib.dump(bst, f"{ART}/model.joblib")
joblib.dump(dict(method=calib["chosen"], model=calibrator), f"{ART}/calibrator.joblib")
joblib.dump(lr_model, f"{ART}/logreg_baseline.joblib")
dump(
    dict(
        features=feats,
        numeric=[f for f in feats if f in NUM],
        categorical=[f for f in feats if f in CAT],
        slice_columns_not_features=SLICES,
        label=LABEL,
    ),
    f"{ART}/feature_list.json",
)
dump(cat_maps, f"{ART}/category_mappings.json")
model_sha = hashlib.sha256(open(f"{ART}/model.txt", "rb").read()).hexdigest()

with mlflow.start_run(run_name="final_lgbm_frozen") as run:
    final_run_id = run.info.run_id
    mlflow.log_params(
        {
            "selected_config": best["name"],
            "search_run_id": best["run_id"],
            "best_iteration": best["best_iteration"],
            "calibration": calib["chosen"],
            "calibration_scheme": calib["scheme"][:500],
            "precision_target": prec_target,
            "low_recall_target": 0.95,
            "min_high_flags": 50,
            "t_high_raw": thr["t_high"],
            "t_low_raw": thr["t_low"],
            "model_sha256": model_sha,
            "train_sha256": hashes["train"]["sha256"],
            "val_sha256": hashes["val"]["sha256"],
            "repro_max_abs_diff": repro_maxdiff,
        }
    )
    mets = {}
    for k, v in cmp["models"].items():
        mets[f"val_{k}_pr_auc"] = v["pr_auc"]
        mets[f"val_{k}_roc_auc"] = v["roc_auc"]
        mets[f"val_{k}_recall_at_rule_fpr"] = v["recall_at_rule_fpr"]
        mets[f"val_{k}_precision_at_rule_recall"] = v["precision_at_rule_recall"]
    for k, v in thr["high_val"].items():
        mets[f"val_high_{k}"] = v
    for b in ("low", "review", "high"):
        mets[f"val_band_{b}_share"] = bands[b]["share"]
        mets[f"val_band_{b}_fraud_rate"] = bands[b]["fraud_rate"]
    mets["val_false_auto_close_per_10k"] = bands["false_auto_close_per_10k_tx"]
    mets["val_brier_raw"] = calib["raw"]["brier"]
    mets[f"val_brier_{chosen}_oof"] = calib[f"{chosen}_oof"]["brier"]
    mlflow.log_metrics({k: float(v) for k, v in mets.items()})
    thresholds_json = dict(
        version="val-frozen-2026-09-29",
        score_space="raw LightGBM probability (model.txt); bands use raw score",
        t_high=thr["t_high"],
        t_low=thr["t_low"],
        t_high_calibrated_prob=thr["t_high_calibrated_prob"],
        t_low_calibrated_prob=thr["t_low_calibrated_prob"],
        bands={
            "high": "score >= t_high -> offer card block (customer confirms) + human handoff",
            "review": "t_low <= score < t_high -> human handoff (review), no block",
            "low": "score < t_low -> agent auto-explains / helps identify merchant, may close",
        },
        scope="transaction_status NOT IN ('Pending','Reversed'); those are handled by deterministic rules",
        selection=dict(
            function="triage.thresholds.select_thresholds",
            precision_target=prec_target,
            precision_target_source="rule fraud_score>=30 VAL precision",
            low_recall_target=0.95,
            min_high_flags=50,
            high_feasible=thr["high_feasible"],
            low_feasible=thr["low_feasible"],
            notes=thr["notes"],
        ),
        val=dict(high=thr["high_val"], low=thr["low_val"], bands=bands),
        calibration=dict(method=calib["chosen"], scheme=calib["scheme"]),
        model_sha256=model_sha,
        mlflow_final_run_id=final_run_id,
        mlflow_search_run_id=best["run_id"],
        data_hashes={s: hashes[s]["sha256"] for s in ("train", "val")},
    )
    dump(thresholds_json, f"{ART}/thresholds.json")
    results = dict(
        selection=selection,
        best=best,
        lr_best=lr_best,
        rule=rule_info,
        hashes=hashes,
        repro_max_abs_diff=repro_maxdiff,
        compare=cmp,
        calibration=calib,
        thresholds=thr,
        bands=bands,
        threshold_stability=halves,
        low_band_tradeoff=tradeoff,
        high_band_fp_fraud_score=high_fp_fraud_score,
        fairness=fair,
        importance=imp.to_dict("records"),
        leakage_single_feature=leak,
        fraud_score_facts=fs_facts,
        search=[
            {
                k: r[k]
                for k in (
                    "name",
                    "run_id",
                    "best_iteration",
                    "pr_auc",
                    "roc_auc",
                    "train_pr_auc",
                    "ablation",
                )
            }
            for r in search
        ],
        lr_runs=lrs,
        final_run_id=final_run_id,
        model_sha256=model_sha,
    )
    dump(results, f"{ART}/val_results.json")
    open(f"{WORK}/fairness_table.md", "w").write(fairness_markdown(fair))
    for f in (
        "model.txt",
        "calibrator.joblib",
        "feature_list.json",
        "category_mappings.json",
        "thresholds.json",
        "val_results.json",
        "logreg_baseline.joblib",
    ):
        mlflow.log_artifact(f"{ART}/{f}", "frozen")
    mlflow.log_artifact(f"{ROOT}/requirements.txt", "env")
print("final run", final_run_id, f"{time.time() - t0:.0f}s")
