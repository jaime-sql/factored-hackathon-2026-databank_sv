"""Stage 1: data verification, rule baseline, LR baseline, LightGBM search. TRAIN/VAL only."""

import copy
import time

import joblib
import lightgbm as lgb
import mlflow
from common import *
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from triage.features import *
from triage.metrics import Ranked, average_precision, confusion_at, roc_auc

mlflow.set_tracking_uri(MLFLOW_URI)
mlflow.set_experiment(EXPERIMENT)
t0 = time.time()
df = load_splits(("train", "val"))
assert "test" not in set(df["split"])
hashes = {}
for s in ("train", "val"):
    sub = df[df.split == s]
    h = sorted_key_hash(sub.transaction_key)
    hashes[s] = dict(
        rows=len(sub),
        positives=int(sub[LABEL].sum()),
        sha256=h,
        manifest_sha256=MANIFEST["splits"][s]["sha256_sorted_ids"],
        match=h == MANIFEST["splits"][s]["sha256_sorted_ids"],
        manifest_rows=MANIFEST["splits"][s]["rows"],
        manifest_positives=MANIFEST["splits"][s]["positives"],
    )
    assert hashes[s]["match"], s
dump(hashes, f"{WORK}/hashes.json")
print(hashes, f"{time.time() - t0:.1f}s")

tr, va = (
    df[df.split == "train"].reset_index(drop=True),
    df[df.split == "val"].reset_index(drop=True),
)
del df
ytr, yva = tr[LABEL].to_numpy(), va[LABEL].to_numpy()
print("nulls train:", tr[NUM].isna().mean()[lambda s: s > 0].to_dict())


def ranking_metrics(score, y):
    tp, fp = Ranked(score, y).curve()
    return dict(pr_auc=average_precision(tp, fp), roc_auc=roc_auc(tp, fp))


# ---- 1. rule baseline
rf = rule_flag(va)
rule = confusion_at(rf.astype(float), yva, 1.0)
rule.update({f"score_{k}": v for k, v in ranking_metrics(va[RULE_SCORE].to_numpy(), yva).items()})
rule_tr = confusion_at(rule_flag(tr).astype(float), ytr, 1.0)
rule["train_flagged"], rule["train_tp"] = rule_tr["flagged"], rule_tr["tp"]
print("rule", rule)
with mlflow.start_run(run_name="baseline_rule_fraud_score_ge_30") as run:
    mlflow.log_params(dict(model="rule", rule="fraud_score >= 30", split_eval="val"))
    mlflow.log_metrics({f"val_{k}": float(v) for k, v in rule.items() if k != "threshold"})
    mlflow.log_dict(hashes, "data_hashes.json")
    rule["run_id"] = run.info.run_id
dump(rule, f"{WORK}/rule.json")
np.save(f"{WORK}/val_rule_score.npy", va[RULE_SCORE].to_numpy(dtype="float64"))

# ---- 2. logistic regression on numeric features (scaled)
lr_res = []
for cw in (None, "balanced"):
    t = time.time()
    pipe = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(C=1.0, class_weight=cw, max_iter=2000, random_state=SEED),
    )
    pipe.fit(tr[NUM].to_numpy(dtype="float64"), ytr)
    p = pipe.predict_proba(va[NUM].to_numpy(dtype="float64"))[:, 1]
    m = ranking_metrics(p, yva)
    with mlflow.start_run(run_name=f"logreg_numeric_cw_{cw}") as run:
        mlflow.log_params(
            dict(
                model="logistic_regression",
                features="numeric (manifest)",
                n_features=len(NUM),
                imputer="median",
                scaler="standard",
                C=1.0,
                class_weight=str(cw),
                seed=SEED,
            )
        )
        mlflow.log_metrics({f"val_{k}": v for k, v in m.items()})
        joblib.dump(pipe, f"{WORK}/lr_{cw}.joblib")
        mlflow.log_artifact(f"{WORK}/lr_{cw}.joblib", "model")
        lr_res.append(
            dict(class_weight=str(cw), run_id=run.info.run_id, **m, path=f"{WORK}/lr_{cw}.joblib")
        )
    np.save(f"{WORK}/val_lr_{cw}.npy", p)
    print("LR", cw, m, f"{time.time() - t:.0f}s")
dump(lr_res, f"{WORK}/lr.json")

# ---- 3. LightGBM search (<=10 configs), early stopping on val PR-AUC
cat_maps = build_cat_maps(tr)
dump(cat_maps, f"{WORK}/cat_maps.json")
card = {
    c: dict(
        train_nunique=int(tr[c].nunique()),
        train_null_rate=float(tr[c].isna().mean()),
        val_unseen_rate=float((~va[c].isin(cat_maps[c]) & va[c].notna()).mean()),
    )
    for c in CAT
}
dump(card, f"{WORK}/cardinality.json")
print(card)
HIGHCARD = ["merchant_name", "transaction_city"]
freq_maps = {
    c: tr[c].astype("object").fillna("__NA__").value_counts(normalize=True).to_dict()
    for c in HIGHCARD
}
spw_sqrt = float(np.sqrt((~ytr).sum() / ytr.sum()))

BASE = dict(
    objective="binary",
    learning_rate=0.05,
    num_leaves=31,
    min_child_samples=200,
    feature_fraction=0.8,
    bagging_fraction=0.8,
    bagging_freq=1,
    lambda_l2=1.0,
    min_data_per_group=200,
    cat_smooth=20.0,
    cat_l2=10.0,
    max_cat_threshold=16,
    metric=["average_precision", "binary_logloss"],
    first_metric_only=True,
    seed=SEED,
    bagging_seed=SEED,
    feature_fraction_seed=SEED,
    data_random_seed=SEED,
    deterministic=True,
    force_col_wise=True,
    num_threads=8,
    verbose=-1,
)
CONFIGS = [
    dict(name="c1_nl31_spw1", cat="native"),
    dict(name="c2_nl31_spw10", cat="native", scale_pos_weight=10.0),
    dict(name="c3_nl31_spwsqrt", cat="native", scale_pos_weight=round(spw_sqrt, 2)),
    dict(name="c4_nl63_mcs500_spw1", cat="native", num_leaves=63, min_child_samples=500),
    dict(name="c5_nl15_mcs1000_spw1", cat="native", num_leaves=15, min_child_samples=1000),
    dict(name="c6_nl31_spw1_drop_highcard", cat="drop"),
    dict(name="c7_nl31_spw1_freqenc_highcard", cat="freq"),
    dict(name="c8_nl63_spw10", cat="native", num_leaves=63, scale_pos_weight=10.0),
]
ABLATION = dict(name="ablation_no_fraud_score", cat="native", drop_features=["fraud_score"])


def matrices(cfg):
    feats = NUM + CAT
    if cfg["cat"] == "drop":
        feats = [f for f in feats if f not in HIGHCARD]
    feats = [f for f in feats if f not in cfg.get("drop_features", [])]
    Xtr, Xva = prepare(tr, cat_maps, feats), prepare(va, cat_maps, feats)
    if cfg["cat"] == "freq":
        for c in HIGHCARD:
            Xtr[c] = tr[c].astype("object").fillna("__NA__").map(freq_maps[c]).astype("float32")
            Xva[c] = (
                va[c]
                .astype("object")
                .fillna("__NA__")
                .map(freq_maps[c])
                .fillna(0)
                .astype("float32")
            )
    return feats, Xtr, Xva


results = []
for cfg in CONFIGS + [ABLATION]:
    t = time.time()
    feats, Xtr, Xva = matrices(cfg)
    params = copy.deepcopy(BASE)
    params.update({k: v for k, v in cfg.items() if k not in ("name", "cat", "drop_features")})
    # fraud_score: legit mass is ~uniform on [0,30) and the fraud tail >=30 is ~0.07% of rows, so
    # default quantile binning (255 bins) merges [~29.9, 100] into one bin. Give it one bin per value.
    params["max_bin_by_feature"] = [5000 if f == "fraud_score" else 255 for f in feats]
    dtr = lgb.Dataset(Xtr, ytr, free_raw_data=True)
    dva = lgb.Dataset(Xva, yva, reference=dtr)
    ev = {}
    bst = lgb.train(
        params,
        dtr,
        num_boost_round=3000,
        valid_sets=[dva],
        valid_names=["val"],
        callbacks=[
            lgb.early_stopping(200, first_metric_only=True, verbose=False),
            lgb.record_evaluation(ev),
            lgb.log_evaluation(0),
        ],
    )
    p = bst.predict(Xva, num_iteration=bst.best_iteration)
    m = ranking_metrics(p, yva)
    ptr = bst.predict(Xtr, num_iteration=bst.best_iteration)
    m["train_pr_auc"] = ranking_metrics(ptr, ytr)["pr_auc"]
    with mlflow.start_run(run_name=f"lgbm_{cfg['name']}") as run:
        mlflow.log_params(
            {
                **{k: (str(v) if isinstance(v, list) else v) for k, v in params.items()},
                "cat_handling": cfg["cat"],
                "n_features": len(feats),
                "features": ",".join(feats),
                "best_iteration": bst.best_iteration,
                "is_ablation": cfg is ABLATION,
            }
        )
        mlflow.log_metrics(
            {f"val_{k}" if not k.startswith("train") else k: v for k, v in m.items()}
        )
        mpath = f"{WORK}/lgbm_{cfg['name']}.txt"
        bst.save_model(mpath, num_iteration=bst.best_iteration)
        mlflow.log_artifact(mpath, "model")
        results.append(
            dict(
                name=cfg["name"],
                cfg=cfg,
                params=params,
                features=feats,
                run_id=run.info.run_id,
                best_iteration=bst.best_iteration,
                model_path=mpath,
                ablation=cfg is ABLATION,
                **m,
            )
        )
    np.save(f"{WORK}/val_lgbm_{cfg['name']}.npy", p)
    print(
        cfg["name"],
        bst.best_iteration,
        {k: round(v, 4) for k, v in m.items()},
        f"{time.time() - t:.0f}s",
        flush=True,
    )
    dump(results, f"{WORK}/lgbm_search.json")
dump(dict(freq_maps=freq_maps, highcard=HIGHCARD), f"{WORK}/freq_maps.json")
print("done", f"{time.time() - t0:.0f}s")
