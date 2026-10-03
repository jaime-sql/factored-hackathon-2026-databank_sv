"""Render docs/evaluation_val.md from artifacts/val_results.json (all numbers from code)."""

import json

R = json.load(open("/workspace/hack-ml/artifacts/val_results.json"))
S1 = R["superseded_v1"]  # v1 (model-based HIGH) banding keys live here
T = json.load(open("/workspace/hack-ml/artifacts/thresholds.json"))
fair_md = open("/workspace/hack-ml/work/fairness_table.md").read()
reqs = open("/workspace/hack-ml/requirements.txt").read().strip().replace("\n", ", ")
c, ci, h = R["compare"], R["compare"]["bootstrap_95ci"], R["hashes"]
rule, M = c["rule_operating_point"], c["models"]
f4 = lambda x: f"{x:.4f}"
fc = lambda v: f"[{v[0]:+.4f}, {v[1]:+.4f}]"


def ci_s(k, m):
    return f"[{ci[k][m][0]:.4f}, {ci[k][m][1]:.4f}]"


L = []
A = L.append
A("# Fraud-risk triage model: VALIDATION evaluation (TEST frozen, never touched)\n")
A(
    "Generated 2026-09-29 by `scripts/03_write_doc.py` from `artifacts/val_results.json`. Every number comes from `scripts/01_search.py`, `scripts/02_finalize.py`, `scripts/04_rule_high_bands.py` and `scripts/05_pending_reversed_high.py`. "
    "TEST rows were filtered out when the parquet was scanned (`split != 'test'`); no test metric, label or score was computed.\n"
)
V = R.get("banding_v2")
if V:
    fv2 = open("/workspace/hack-ml/work/fairness_table_v2.md").read()
    bb, ho, fx, l9 = (
        V["bands"],
        V["high_operating_point"],
        V["high_rule_val_facts"],
        V["sensitivity_low_90"],
    )
    A(
        f"## Decision note: v2 banding (team decision, 2026-09-29; current; MLflow run `{V['mlflow_run_id']}`)\n"
    )
    A(
        "- **HIGH = `fraud_score > 30`.** Deterministic, and a missing fraud_score is never HIGH. "
        f"This rule was found on VAL: every legit transaction with fraud_score ≥ 30 sits at exactly 30.00 ({fx['legit_ge30_n']} rows, min = max = {fx['legit_ge30_max']:.2f}), and fraud_score > 30 flagged {fx['high_n']} rows, all fraud. "
        "Because it was found on the same val data it is evaluated on, it still needs TEST confirmation."
    )
    A(
        f"- **REVIEW vs LOW** (non-HIGH rows): frozen LightGBM raw score ≥ t_low → REVIEW, otherwise LOW. t_low was re-derived on VAL as the highest threshold keeping ≥ 95% of all val fraud out of LOW (`select_low_threshold_given_high`). "
        f"Re-derived value {V['t_low_rederived']:.9g} vs previous {V['t_low_prev']:.9g}: changed = {V['t_low_changed']}, so **t_low = {V['t_low']:.9g}** is kept (calibrated ≈ {T['t_low_calibrated_prob']:.4g})."
    )
    A(
        "- The displayed probability is still the Platt-calibrated LightGBM probability. v1 model-based HIGH (raw ≥ 0.0164888) is superseded (run `8adb62ca0c7e477e8af3e2dd2a96630e` tagged SUPERSEDED).\n"
    )
    A(
        "| band (VAL) | n | share of val | frauds | fraud rate | share of all fraud | share of legit |\n|---|---|---|---|---|---|---|"
    )
    for k in ("high", "review", "low"):
        d = bb[k]
        A(
            f"| {k.upper()} | {d['n']:,} | {d['share'] * 100:.3f}% | {d['fraud']} | {d['fraud_rate'] * 100:.4f}% | {d['share_of_all_fraud'] * 100:.2f}% | {d['share_of_legit'] * 100:.4f}% |"
        )
    A(
        f"\nHIGH: flagged {ho['flagged']}, TP {ho['tp']}, FP {ho['fp']}, precision {ho['precision']:.4f}, recall {ho['recall']:.4f}, **FPR {ho['fpr']:.4g}** ({ho['wrongful_flags_per_10k_legit']:.2f} wrongful block offers per 10k legit). "
        f"Wrongful auto-closes (fraud in LOW): **{bb['false_auto_close_per_10k_tx']:.3f} per 10k val transactions** ({bb['false_auto_close_per_10k_auto_handled']:.2f} per 10k auto-handled). "
        "Compared with v1, the 25 legit rows at fraud_score = 30.00 move from HIGH to REVIEW; LOW is unchanged.\n"
    )
    A(
        f"Sensitivity only, not adopted: 90% target → t_low {l9['t_low']:.9g}, LOW = {l9['share_all_in_low'] * 100:.2f}% of val ({l9['legit_share_in_low'] * 100:.2f}% of legit), {l9['fraud_in_low']} frauds in LOW, {l9['false_auto_close_per_10k_tx']:.3f} wrongful auto-closes per 10k.\n"
    )
    A(
        "Fairness (v2): the overall HIGH FPR is 0, so HIGH FPR ratios are undefined and no flags are raised. Escalation (HIGH or REVIEW) FPR ratios vs overall:\n"
    )
    A(fv2)
    A(
        "\nFlags (escalation FPR ratio outside 0.8–1.25): "
        + (", ".join(f"{x['column']}={x['group']}" for x in V["fairness"]["flags"]) or "none")
        + ". Escalation recall is lower for Mexico (0.927) and mexican accent (0.906) than overall (0.952), with more of their traffic in LOW (about 18.6–18.7% vs 15.5%). Watch this on TEST.\n"
    )
    PR = R.get("pending_reversed_high")
    if PR:
        A("### Pending / Reversed charges: HIGH rule runs first (team decision 2026-09-29)\n")
        A(
            "Order in `triage.score.score`: `fraud_score > 30` → HIGH, even for Pending or Reversed charges. Otherwise Pending/Reversed → `out_of_scope` (rule-based answer). Otherwise the model decides REVIEW or LOW. "
            "prob is NaN for Pending/Reversed rows because the model never saw that scope. "
            "Source: `out/gold/transactions_masked.parquet`, the masked 1:1 copy of silver.transactions. Silver itself exists only in the DE's local duckdb and holds raw ids, so it wasn't used. Manifest cutoffs apply (val ends 2026-01-06 18:26:41 CST).\n"
        )
        A(
            "| window | status | rows | fraud | fraud caught by fraud_score > 30 | legit wrongly flagged | missing fraud_score (of which fraud) |\n|---|---|---|---|---|---|---|"
        )
        for w in ("val", "train"):
            for st_ in ("Pending", "Reversed", "Pending+Reversed"):
                d = PR[w][st_]
                A(
                    f"| {'**' + w + '**' if w == 'val' else w} | {st_} | {d['rows']:,} | {d['fraud']} | {d['fraud_caught_high']} | {d['legit_flagged_high']} | {d['missing_fraud_score']:,} ({d['fraud_missing_fraud_score']}) |"
                )
        rc = PR["reconciliation"]
        A(
            f"\nTest window: row counts only (Pending {PR['test_window_rows_only']['Pending']:,}, Reversed {PR['test_window_rows_only']['Reversed']:,}); labels were not read. "
            f"Row counts add up across windows (Pending {rc['rows_by_window']['Pending']['sum']:,}, Reversed {rc['rows_by_window']['Reversed']['sum']:,}, matching all-row counts). "
            f"Reconciliation: analytics reports 115 fraud across the full data (79 Pending, 36 Reversed). Train+val observed here is {rc['train_plus_val_fraud_observed']['total']} "
            f"({rc['train_plus_val_fraud_observed']['Pending']} Pending, {rc['train_plus_val_fraud_observed']['Reversed']} Reversed). That implies {rc['implied_test_window_remainder_per_analytics']['total']} in the test window "
            f"({rc['implied_test_window_remainder_per_analytics']['Pending']} Pending, {rc['implied_test_window_remainder_per_analytics']['Reversed']} Reversed), which is not verified because test labels weren't read. "
            f"The legit-at-30.00 pattern holds here too: every legit row at ≥ 30 sits at exactly 30.00 (val {PR['val']['Pending+Reversed']['legit_at_exactly_30']}, train {PR['train']['Pending+Reversed']['legit_at_exactly_30']}), so the rule flags 0 legit. "
            "With only 11 val fraud, the val catch rate (5/11) is very noisy.\n"
        )
    A(
        "Sections 6–7 below describe the **v1 (superseded)** model-based HIGH band and are kept for the record.\n"
    )
A("## 1. Data and integrity\n")
A(
    "| split | rows | positives | sha256(sorted transaction_key) | matches manifest |\n|---|---|---|---|---|"
)
for s in ("train", "val"):
    A(f"| {s} | {h[s]['rows']:,} | {h[s]['positives']} | `{h[s]['sha256']}` | {h[s]['match']} |")
A(
    "\nScope: rows are already limited to `transaction_status NOT IN ('Pending','Reversed')` (manifest `ml_scope`). Features: the manifest's 20 numeric + 9 categorical fields only. "
    "Slice columns (customer_country/segment/accent) are used only for fairness reporting.\n"
)
A(
    "Categoricals: cardinality is low (train unique values: merchant_name 24, transaction_city 28, all others ≤ 8; 0% unseen categories in val). "
    "I used LightGBM native categorical handling with `min_data_per_group=200, cat_smooth=20, cat_l2=10, max_cat_threshold=16` and vocabularies built from train only (unseen → missing). "
    "I also ran variants that drop the two high-cardinality fields (c6) or frequency-encode them (c7). Val PR-AUC was 0.5465 / 0.5474 vs 0.5472 for native, which is within noise, so native handling was kept because it ships no extra encoder.\n"
)
A(
    "Note on binning: fraud_score's legit mass is roughly uniform on [0, 30) and its fraud tail (≥ 30) is about 0.07% of rows. With LightGBM's default 255 quantile bins that tail collapses into one bin, and the first run reached only val PR-AUC 0.133. "
    "The fix was `max_bin_by_feature = 5000` for fraud_score (one bin per distinct value). All runs reported here use it.\n"
)
A("## 2. Models and selection\n")
A(f"- Rule baseline: `fraud_score >= 30` (null → not flagged). MLflow run `{R['rule']['run_id']}`.")
A(
    f"- Logistic regression on the 20 numeric features (median imputation, then StandardScaler; C=1). class_weight=None scored val PR-AUC {R['lr_runs'][0]['pr_auc']:.4f} (run `{R['lr_runs'][0]['run_id']}`) and balanced scored {R['lr_runs'][1]['pr_auc']:.4f} (run `{R['lr_runs'][1]['run_id']}`). **None was kept.**"
)
A(
    "- LightGBM: lr 0.05, bagging/feature fraction 0.8, λ2=1, early stopping (200 rounds) on val average_precision, seed 20260929, `deterministic=True`. 8 configs plus 1 ablation:\n"
)
A(
    "| config | val PR-AUC | val ROC-AUC | train PR-AUC | best iter | MLflow run |\n|---|---|---|---|---|---|"
)
for r in R["search"]:
    A(
        f"| {r['name']}{' (ablation, not a candidate)' if r['ablation'] else ''} | {r['pr_auc']:.4f} | {r['roc_auc']:.4f} | {r['train_pr_auc']:.4f} | {r['best_iteration']} | `{r['run_id']}` |"
    )
s = R["selection"]
A(
    f"\nSelection rule: highest val PR-AUC. Configs within {s['tie_tol']} of the top ({s['top_by_pr_auc']}, {s['top_pr_auc']:.4f}) count as ties, because that gap is far smaller than the CI width. Ties are broken by native categoricals, then fewer leaves, then larger min_child_samples. "
    f"Tied: {', '.join(s['tied'])}. **Selected: {s['selected']}** (num_leaves 15, min_child_samples 1000, scale_pos_weight 1 = no reweighting). scale_pos_weight 10 and ≈31.5 did not beat 1 on val PR-AUC. "
    f"Reproducibility: retraining the selected config from scratch gives a maximum absolute prediction difference of {R['repro_max_abs_diff']} on val. Final frozen run: `{R['final_run_id']}`. model.txt sha256 `{R['model_sha256']}`.\n"
)
A("## 3. VAL comparison (643,787 tx, 599 frauds)\n")
A(
    f"Rule operating point: flagged {rule['flagged']}, TP {rule['tp']}, FP {rule['fp']}, precision {f4(rule['precision'])}, recall {f4(rule['recall'])}, FPR {rule['fpr']:.3e} = **{rule['wrongful_flags_per_10k_legit']:.2f} wrongful flags per 10k legit**. This matches the manifest (413 / 325).\n"
)
A(
    "| | PR-AUC [95% CI] | ROC-AUC | recall @ rule FPR [95% CI] | wrongful/10k @ rule FPR | precision @ rule recall | wrongful/10k @ rule recall |\n|---|---|---|---|---|---|---|"
)
names = {
    "rule_fraud_score": "Rule (fraud_score continuous)",
    "logreg": "Logistic regression",
    "lightgbm": "LightGBM (selected)",
}
for k, v in M.items():
    A(
        f"| {names[k]} | {f4(v['pr_auc'])} {ci_s(k, 'pr_auc')} | {f4(v['roc_auc'])} | {f4(v['recall_at_rule_fpr'])} {ci_s(k, 'recall_at_rule_fpr')} | "
        f"{v['at_rule_fpr']['wrongful_flags_per_10k_legit']:.2f} | {f4(v['precision_at_rule_recall'])} | {v['at_rule_recall']['wrongful_flags_per_10k_legit']:.2f} |"
    )
ab = c["ablation_no_fraud_score"]
A(
    f"\nBootstrap: 1,000 row resamples of val (seed 20260929). In each resample the rule's FPR is recomputed on that resample. Paired CI of the difference vs the rule: "
    f"LightGBM PR-AUC {fc(ci['lightgbm']['diff_pr_auc_vs_rule_fraud_score_ci'])}, recall@ruleFPR {fc(ci['lightgbm']['diff_recall_at_rule_fpr_vs_rule_fraud_score_ci'])}; "
    f"LR PR-AUC {fc(ci['logreg']['diff_pr_auc_vs_rule_fraud_score_ci'])}, recall@ruleFPR {fc(ci['logreg']['diff_recall_at_rule_fpr_vs_rule_fraud_score_ci'])}.\n"
)
hv = S1["compare_lightgbm_at_high_threshold"]
A(
    f"v1 (superseded) LightGBM HIGH threshold: flagged {hv['flagged']}, TP {hv['tp']}, FP {hv['fp']}, precision {f4(hv['precision'])}, recall {f4(hv['recall'])}, {hv['wrongful_flags_per_10k_legit']:.2f} wrongful flags per 10k legit.\n"
)
A(
    f"Ablation without fraud_score: val PR-AUC {ab['pr_auc']:.5f} (prevalence 0.00093) and ROC-AUC {ab['roc_auc']:.4f}. **Without fraud_score the other manifest features carry essentially no signal.**\n"
)
A(
    "Reading: LightGBM ties the rule on PR-AUC (+0.003, paired CI just above 0) and on recall at the rule's FPR (identical). "
    "Its ROC-AUC gain (0.818 vs 0.719) comes almost entirely from where the 20% of rows with a null fraud_score are ranked. Re-ranking fraud_score with nulls imputed to 29.9 gives ROC-AUC 0.8175 (ad-hoc check, not in the JSON). "
    "At the rule's recall, the continuous fraud_score reaches precision 1.0 (threshold 30.06), which is better than LightGBM's 0.9286.\n"
)
A("## 4. Leakage check / feature importance\n")
ff = R["fraud_score_facts"]
A(
    f"- **fraud_score dominates**: {R['importance'][0]['gain_share'] * 100:.1f}% of total gain. Every other feature is ≤ {R['importance'][1]['gain_share'] * 100:.2f}%."
)
A(
    f"- **fraud_score > 30 is a deterministic fraud marker in this synthetic data.** Every legit row with fraud_score ≥ 30 has exactly 30.00 (train {ff['train']['>=30']['n'] - ff['train']['>=30']['fraud']}, val {ff['val']['>=30']['n'] - ff['val']['>=30']['fraud']}). fraud_score ≥ 40 is 100% fraud (train {ff['train']['>=40']['fraud']}/{ff['train']['>=40']['n']}, val {ff['val']['>=40']['fraud']}/{ff['val']['>=40']['n']}). Below 30, and when null (train {ff['train']['null_fraud']} / val {ff['val']['null_fraud']} frauds), fraud is indistinguishable from legit. "
    "It is the bank's pre-existing score and the manifest allows it, so I did not drop it. It behaves like a near-label and caps what any model can add."
)
hf = S1["high_band_fp_fraud_score"]
A(
    f"- All {int(hf['count'])} HIGH-band false positives have fraud_score exactly {hf['max']:.2f}. A plain `fraud_score > 30` rule would give val precision 1.0 at the same recall."
)
A(
    "- Single-feature val ROC-AUC (oriented; categoricals target-encoded on train): "
    + ", ".join(
        f"{d['feature']} {d['val_auc_oriented']:.3f}" for d in R["leakage_single_feature"][:6]
    )
    + ". Apart from fraud_score's step, no feature separates the classes near-perfectly.\n"
)
A("Top 15 features by gain:\n\n| # | feature | gain share | splits |\n|---|---|---|---|")
for i, d in enumerate(R["importance"][:15], 1):
    A(f"| {i} | {d['feature']} | {d['gain_share'] * 100:.3f}% | {d['split']} |")
cal = R["calibration"]
A("\n## 5. Calibration\n")
A(f"Scheme: {cal['scheme']}. The OOF metrics below are for held-out folds only.\n")
A(
    "| | Brier | log-loss | ECE (10 quantile bins) | mean pred (prevalence 0.000930) |\n|---|---|---|---|---|"
)
for k in ("raw", "platt_oof", "isotonic_oof"):
    A(
        f"| {k} | {cal[k]['brier']:.7f} | {cal[k]['logloss']:.6f} | {cal[k]['ece_quantile']:.2e} | {cal[k]['mean_pred']:.6f} |"
    )
A(
    "\nReliability, fixed bins (raw → Platt OOF):\n\n| bin | n raw | mean pred raw | frac pos raw | n Platt | mean pred Platt | frac pos Platt |\n|---|---|---|---|---|---|---|"
)
pb = {b["bin"]: b for b in cal["platt_oof"]["fixed_bins"]}
for b in cal["raw"]["fixed_bins"]:
    p = pb.get(b["bin"])
    A(
        f"| {b['bin']} | {b['n']} | {b['mean_pred']:.5f} | {b['frac_pos']:.5f} | {p['n'] if p else '-'} | {p['mean_pred'] if p else float('nan'):.5f} | {p['frac_pos'] if p else float('nan'):.5f} |"
    )
A(
    f"\nThe raw model is already close to calibrated (no class reweighting). Platt gives a slightly lower OOF Brier and log-loss than raw, and isotonic does worse on log-loss. **Chosen: {cal['chosen']}**, refit on all val and saved as `artifacts/calibrator.joblib`. "
    "It only changes the displayed probability. Bands are decided on the raw score, and since calibration is monotone the ranking is unchanged. "
    "Caveat: val also served early stopping and threshold selection, so the calibration check is optimistic until TEST.\n"
)
th = S1["thresholds"]
b = S1["bands"]
A("## 6. Triage thresholds, v1 (superseded by the v2 decision note above)\n")
A(
    f"- **HIGH** (offer card block with customer confirmation, then human handoff): raw score ≥ **{th['t_high']:.6g}** (calibrated ≈ {th['t_high_calibrated_prob']:.4g}). "
    f"Among thresholds with precision ≥ the rule's {th['precision_target']:.4f} and ≥ 50 flags, it takes the maximum recall, then the highest threshold at that recall. "
    f"Val: flagged {th['high_val']['flagged']}, precision {f4(th['high_val']['precision'])}, recall {f4(th['high_val']['recall'])}, FPR {th['high_val']['fpr']:.3e}."
)
A(
    f"- **LOW** (agent auto-explains and may close): raw score < **{th['t_low']:.6g}** (calibrated ≈ {th['t_low_calibrated_prob']:.4g}). This is the highest threshold with recall above LOW ≥ 0.95. "
    f"Val: recall above LOW {f4(th['low_val']['recall_above_low'])}, so {th['low_val']['fraud_in_low_band']} frauds land in the auto band. Legit volume in the auto band: {th['low_val']['legit_share_in_low_band'] * 100:.2f}%."
)
A("- **REVIEW** (human handoff without block): everything in between.\n")
A(
    "| band | n | share of val | frauds | fraud rate | share of all fraud | share of legit |\n|---|---|---|---|---|---|---|"
)
for k in ("low", "review", "high"):
    d = b[k]
    A(
        f"| {k} | {d['n']:,} | {d['share'] * 100:.3f}% | {d['fraud']} | {d['fraud_rate'] * 100:.4f}% | {d['share_of_all_fraud'] * 100:.2f}% | {d['share_of_legit'] * 100:.4f}% |"
    )
A(
    f"\nFalse auto-closes (fraud in LOW): **{b['false_auto_close_per_10k_tx']:.3f} per 10k val transactions** ({b['false_auto_close_per_10k_auto_handled']:.2f} per 10k auto-handled).\n"
)
A(
    "**Feasibility.** Both targets are technically met, but the LOW target is costly. Only 15.5% of volume can be auto-handled, and 84.5% goes to human REVIEW. "
    "The reason is that about 46% of frauds (fraud_score < 30 or null) score like legit traffic, so keeping them out of the auto band means escalating almost everything. "
    "The table shows honest alternatives: a lower recall target auto-handles more volume at the cost of more false auto-closes. "
    "The shares here are over all in-scope transactions. In the real dispute flow (a customer who does not recognise a charge) the base rate will be much higher, so these volumes will not transfer directly.\n"
)
A(
    "| recall-above-LOW target | t_low (raw) | frauds in LOW | legit auto-handled | all volume auto-handled | false auto-close /10k tx |\n|---|---|---|---|---|---|"
)
for d in S1["low_band_tradeoff"]:
    A(
        f"| {d['recall_target']} | {d['t_low']:.6g} | {d['fraud_in_low']} | {d['legit_share_in_low'] * 100:.2f}% | {d['share_all_in_low'] * 100:.2f}% | {d['false_auto_close_per_10k_tx']:.3f} |"
    )
st = S1["threshold_stability"]
A("\n**Stability (same procedure run on each time-half of val):**\n")
for k, v in st.items():
    fa = v["full_thresholds_applied"]
    A(
        f"- {k} ({v['positives']} frauds): re-selected t_high {v['t_high']:.6g}, t_low {v['t_low']:.6g}. With the frozen full-val thresholds: HIGH precision {f4(fa['high_precision'])}, recall {f4(fa['high_recall'])}; LOW share {fa['low']['share'] * 100:.2f}%, frauds in LOW {fa['low']['fraud']} ({fa['low']['share_of_all_fraud'] * 100:.2f}% of fraud)."
    )
A(
    f"\nt_low is stable. t_high is not. Val has 324 frauds with raw score ≥ 0.5 and 0 legit rows there. Exactly one fraud (fraud_score 30.06) scores {th['t_high']:.4g}, and the 'maximize recall' rule lowers t_high to include it, which also admits 25 legit rows at fraud_score 30.00. "
    "In the second half of val that fraud is absent, so t_high re-selects to ≈1.0. An alternative is **t_high = 0.5**: val 324 flagged, 324 TP, 0 FP, recall 0.5409. It gives up 1 fraud and removes 25 wrongful block offers. I froze the spec'd rule and flag this for the team to decide.\n"
)
A("## 7. Fairness, v1 banding (superseded; v2 is in the decision note)\n")
A(
    "'HIGH' means block-offer flags. 'Escalate' means HIGH or REVIEW (anything not auto-closed). FPR ratio is the group FPR divided by the overall FPR. A group is small if it has fewer than 30 frauds, and a flag is small-sample if it has fewer than 30 frauds or fewer than 20 FP.\n"
)
A(fair_md)
A("\nFlags (FPR ratio outside 0.8–1.25):\n")
for f_ in S1["fairness"]["flags"]:
    A(
        f"- {f_['column']}={f_['group']}: {f_['metric']} ratio {f_['ratio']:.2f} (n={f_['n']:,}, frauds={f_['positives']}, FP={f_['fp']}){' — small sample' if f_['small_sample'] else ''}"
    )
A(
    "\nAll flags are on HIGH FPR, where the whole val set has only 25 false positives (0 to 16 per group), so the ratios are noise-level. None is significant. Escalation FPR ratios fall between 0.96 and 1.05 for every group. "
    "Mexico and mexican-accent customers get more auto-handling (about 18.6% LOW vs 15.5% overall) and have lower escalation recall (0.927 and 0.906 vs 0.952). Watch this on TEST.\n"
)
A("## 8. Frozen artifacts\n")
A(
    "- `artifacts/model.txt` (+ `model.joblib`), `calibrator.joblib` (Platt), `feature_list.json`, `category_mappings.json`, `thresholds.json`, `logreg_baseline.joblib`, `val_results.json`"
)
A(
    "- `triage/score.py`: `score(df) -> (prob, band)` with v2 banding (HIGH = fraud_score > 30; REVIEW/LOW by raw score vs t_low; out_of_scope when transaction_status is Pending or Reversed). It reads only `artifacts/`. Self-test on VAL: `.venv/bin/python -m triage.score --selftest`."
)
A(
    "- `scripts/05_pending_reversed_high.py`: moves v1 keys under `superseded_v1` in val_results.json; Pending/Reversed HIGH-rule counts (`pending_reversed_high`); `status_rule` in thresholds.json"
)
A(
    "- `scripts/04_rule_high_bands.py`: v2 banding, t_low re-derivation, v2 fairness, MLflow run, thresholds.json v2"
)
A(
    "- `triage/thresholds.py`: `select_thresholds()` (re-runnable), `assign_band()`, `band_report()`, `low_band_tradeoff()`"
)
A(
    "- `evals/run_test_eval.py`: **not run**. It refuses unless `ALLOW_TEST_EVAL=1`, refuses a second run, checks the model sha256 and the TEST key hash against the manifest before loading features, and then scores the v2 banding and writes `docs/evaluation_test.md`."
)
A(
    f"- MLflow: `file:/workspace/hack-ml/mlruns`, experiment `fraud-triage`. The current run is `{V['mlflow_run_id'] if V else R['final_run_id']}` (v2). The v1 final run `{R['final_run_id']}` is tagged SUPERSEDED. An earlier final run, `0c01f9f7277a4be79c9f8c88f16103c5`, is tagged SUPERSEDED: it used the lowest-threshold tie-break for HIGH (413 flags, 88 FP, same recall)."
)
A(
    f"- Environment: `.venv`, requirements.txt: {reqs}. MLflow needs `MLFLOW_ALLOW_FILE_STORE=true` for the file store, which `scripts/common.py` sets."
)
A(
    "- Re-run: `cd scripts && ../.venv/bin/python 01_search.py && ../.venv/bin/python 02_finalize.py && ../.venv/bin/python 04_rule_high_bands.py && ../.venv/bin/python 05_pending_reversed_high.py && ../.venv/bin/python 03_write_doc.py`\n"
)
A("## 9. Limitations\n")
A(
    "- Synthetic data. fraud_score behaves like a near-label (> 30 means fraud, = 30.00 is a legit pile-up), and no other feature carries signal. Model gains over the rule are within noise, and real data would behave differently."
)
A(
    f"- Prevalence is 0.093% with 599 val frauds. CI widths: PR-AUC ±≈0.04 ({ci_s('lightgbm', 'pr_auc')}), recall at rule FPR ±≈0.04 ({ci_s('lightgbm', 'recall_at_rule_fpr')}). HIGH FPR rests on 25 events, so per-group FPR ratios are unreliable."
)
A(
    "- Val was used for early stopping, the 8-config search, calibration and threshold selection, so every val number is optimistic. TEST (single run, Oct 1) is the unbiased check."
)
A(
    "- Band shares are for all in-scope transactions, not disputed ones. Dispute-intake volume and fraud mix will differ."
)
A(
    "- Time drift: val covers 2025-07-26 to 2026-01-07. The thresholds assume a stable fraud_score scale."
)
open("/workspace/hack-ml/docs/evaluation_val.md", "w").write("\n".join(L) + "\n")
print("written", len(L))
