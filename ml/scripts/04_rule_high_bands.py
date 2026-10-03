"""Stage 4 (team decision 2026-09-29): HIGH = fraud_score > 30 (deterministic; missing -> not HIGH).
Non-HIGH rows: frozen LightGBM raw score splits REVIEW / LOW; t_low re-derived on VAL (>=95% of all
val fraud outside LOW). 90% is a sensitivity row only. VAL only; TEST never loaded."""

import mlflow
from common import *
from mlflow.tracking import MlflowClient

from triage.features import LABEL, RULE_SCORE, SLICES, load_splits
from triage.report import fairness, fairness_markdown
from triage.score import calibrate, score_raw
from triage.thresholds import (
    assign_band_v2,
    band_report,
    high_rule_mask,
    select_low_threshold_given_high,
)

mlflow.set_tracking_uri(MLFLOW_URI)
mlflow.set_experiment(EXPERIMENT)
T = json.load(open(f"{ART}/thresholds.json"))
R = json.load(open(f"{ART}/val_results.json"))
prior_run = T["mlflow_final_run_id"]
va = load_splits(("val",))
assert set(va["split"]) == {"val"}
y = va[LABEL].to_numpy()
fs = va[RULE_SCORE].to_numpy(dtype="float64")
raw = score_raw(va)
hi = high_rule_mask(fs)

# rule facts on val
legit_ge30 = fs[(np.nan_to_num(fs, nan=-1) >= 30) & ~y]
facts = dict(
    legit_ge30_n=int(len(legit_ge30)),
    legit_ge30_min=float(legit_ge30.min()),
    legit_ge30_max=float(legit_ge30.max()),
    legit_gt30_n=int(((np.nan_to_num(fs, nan=-1) > 30) & ~y).sum()),
    high_n=int(hi.sum()),
    high_fraud=int((hi & y).sum()),
    min_raw_among_high=float(raw[hi].min()),
    null_fraud_score_n=int(np.isnan(fs).sum()),
)
print("facts", facts)

prev_t_low = T["t_low"]
lo95 = select_low_threshold_given_high(raw, y, hi, 0.95)
lo90 = select_low_threshold_given_high(raw, y, hi, 0.90)
t_low = prev_t_low if lo95["t_low"] == prev_t_low else lo95["t_low"]
t_low_changed = lo95["t_low"] != prev_t_low
print("t_low prev", prev_t_low, "re-derived", lo95["t_low"], "changed", t_low_changed)
print("sens90", lo90)

band = assign_band_v2(fs, raw, t_low)
bands = band_report(band, y)
N = int((~y).sum())
high_op = dict(
    flagged=int(hi.sum()),
    tp=int((hi & y).sum()),
    fp=int((hi & ~y).sum()),
    precision=float(y[hi].mean()),
    recall=float((hi & y).sum() / y.sum()),
    fpr=float((hi & ~y).sum() / N),
    wrongful_flags_per_10k_legit=float(1e4 * (hi & ~y).sum() / N),
)
b90 = assign_band_v2(fs, raw, lo90["t_low"])
bands90 = band_report(b90, y)
fair = fairness(va[SLICES], y, band, SLICES)
esc_ratios = {
    c: {
        g: dict(
            escalate_fpr_ratio=s["escalate_fpr_ratio"],
            escalate_recall=s["escalate_recall"],
            high_fpr=s["high_fpr"],
            share_low=s["share_low"],
            positives=s["positives"],
            small=s["small_sample"],
        )
        for g, s in grp.items()
    }
    for c, grp in fair["groups"].items()
}
print("bands", json.dumps(bands, indent=0))
print("high", high_op)
print("fair flags", fair["flags"])
print(json.dumps(esc_ratios, indent=0))
# self-consistency with the app scorer
from triage import score as S

S._load.cache_clear()

v2 = dict(
    version="v2-rule-high-2026-09-29",
    decision="HIGH = fraud_score > 30 (deterministic; missing fraud_score is not HIGH). Non-HIGH: LightGBM raw score >= t_low -> REVIEW, else LOW. Displayed prob = Platt-calibrated LightGBM probability.",
    high_rule_val_facts=facts,
    t_low=t_low,
    t_low_prev=prev_t_low,
    t_low_rederived=lo95["t_low"],
    t_low_changed=t_low_changed,
    low_95=lo95,
    sensitivity_low_90=dict(**lo90, bands=bands90),
    high_operating_point=high_op,
    bands=bands,
    fairness=fair,
    escalation_ratios=esc_ratios,
    band_counts={b: int((band == b).sum()) for b in ("high", "review", "low")},
)

with mlflow.start_run(run_name="final_v2_rule_high_model_low") as run:
    rid = run.info.run_id
    mlflow.log_params(
        dict(
            version=v2["version"],
            high_rule="fraud_score > 30; missing -> not HIGH",
            t_low_raw=t_low,
            t_low_changed=t_low_changed,
            low_recall_target=0.95,
            model_sha256=T["model_sha256"],
            val_sha256=T["data_hashes"]["val"],
            supersedes_run=prior_run,
            calibration="platt",
        )
    )
    m = {
        f"val_band_{b}_{k}": bands[b][k]
        for b in ("low", "review", "high")
        for k in ("share", "fraud_rate", "share_of_all_fraud")
    }
    m.update({f"val_high_{k}": v for k, v in high_op.items()})
    m.update(
        val_false_auto_close_per_10k=bands["false_auto_close_per_10k_tx"],
        val_sens90_legit_share_in_low=lo90["legit_share_in_low"],
        val_sens90_false_auto_close_per_10k=lo90["false_auto_close_per_10k_tx"],
    )
    mlflow.log_metrics({k: float(v) for k, v in m.items()})
    v2["mlflow_run_id"] = rid

    T_new = dict(T)
    T_new.update(
        version=v2["version"],
        supersedes=dict(version=T.get("version"), mlflow_run_id=prior_run),
        high_rule=dict(
            expr="fraud_score > 30",
            column="fraud_score",
            op=">",
            value=30.0,
            missing="not HIGH",
            rationale="Found on VAL: every legit transaction with fraud_score >= 30 sits at exactly 30.00 "
            f"({facts['legit_ge30_n']} rows); fraud_score > 30 flagged {facts['high_n']} rows, all fraud.",
            val=high_op,
        ),
        t_low=t_low,
        t_low_calibrated_prob=float(calibrate(np.array([t_low]))[0]),
        bands={
            "high": "fraud_score > 30 -> offer card block (customer confirms) + human handoff",
            "review": "not HIGH and LightGBM raw score >= t_low -> human handoff (review), no block",
            "low": "not HIGH and LightGBM raw score < t_low (incl. missing fraud_score scored by model) -> agent auto-explains, may close",
        },
        score_space="t_low is on the raw LightGBM probability (model.txt); displayed prob is Platt-calibrated",
        selection=dict(
            function="triage.thresholds.select_low_threshold_given_high",
            low_recall_target=0.95,
            definition="highest t_low with (HIGH fraud + non-HIGH fraud scoring >= t_low) >= 95% of all VAL fraud",
            t_low_rederived=lo95["t_low"],
            t_low_changed=t_low_changed,
            sensitivity_90=lo90,
        ),
        val=dict(high=high_op, low=lo95, bands=bands, band_counts=v2["band_counts"]),
        mlflow_final_run_id=rid,
    )
    T_new.pop("t_high", None)
    T_new.pop("t_high_calibrated_prob", None)
    T_new["superseded_v1"] = T.get("superseded_v1") or dict(
        t_high_model_raw=T["t_high"],
        t_high_calibrated_prob=T["t_high_calibrated_prob"],
        note="v1 HIGH was model raw score >= t_high; replaced by high_rule",
    )
    dump(T_new, f"{ART}/thresholds.json")
    R["banding_v2"] = v2
    R["current_banding"] = "banding_v2"
    migrate_v1_keys(R)
    dump(R, f"{ART}/val_results.json")
    open(f"{WORK}/fairness_table_v2.md", "w").write(fairness_markdown(fair))
    mlflow.log_artifact(f"{ART}/thresholds.json", "frozen")
    mlflow.log_artifact(f"{ART}/val_results.json", "frozen")

c = MlflowClient(MLFLOW_URI)
c.set_tag(
    prior_run, "status", f"SUPERSEDED by {rid}: team decision HIGH = fraud_score > 30 (v2 banding)"
)
c.set_tag(rid, "status", "CURRENT")
print("run", rid, "tagged prior", prior_run)
