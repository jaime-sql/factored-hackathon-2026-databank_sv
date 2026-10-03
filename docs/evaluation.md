# Evaluation: fraud-risk triage (frozen model, single TEST run)

All numbers below come from two runs on 2026-10-03 (CST):
- **TEST**: `ml/evals/run_test_eval.py`, run once at 09:15 CST, MLflow run `6b8156af68a440988e2ff36640aca29b`, raw output `work/test_results.json` (copy in `artifacts/test_results.json`, auto table in `docs/evaluation_test.md`). TEST key hash `fbc11459…397390a` matched `splits_manifest.json` before any label was read.
- **VALIDATION**: `work/val_routing_mexico.py` and `work/mexico_drill.py` → `work/val_routing_mexico.json`; LightGBM VAL scores cached in `work/val_lgbm_scores.npy` (identical to the earlier search cache for c5).

Frozen config, nothing tuned on TEST: LightGBM `c5_nl15_mcs1000_spw1` (`artifacts/model.txt`, sha256 `fb972233…de6884`), `thresholds.json` v2, `t_low = 0.000275603870032301` (raw score).
Routing order: (1) HIGH = `fraud_score > 30` (strict, missing ≠ HIGH), any status → (2) Pending/Reversed → deterministic rule → (3) Approved/Declined → REVIEW if score ≥ t_low, else LOW.

## 1. TEST: model vs rule vs logistic regression (Approved/Declined, 643,788 charges, 574 fraud)

| metric | rule (`fraud_score` as score) | logreg baseline | LightGBM |
|---|---|---|---|
| PR-AUC [95% bootstrap CI] | 0.5833 [0.5468, 0.6229] | 0.5760 [0.5393, 0.6168] | 0.5840 [0.5474, 0.6232] |
| ROC-AUC | 0.7236 | 0.7801 | 0.8403 |
| recall at 0.02% FPR | 0.5819 (334 TP, 88 FP) | 0.5732 (329 TP, 128 FP) | 0.5819 (334 TP, 128 FP) |

**Finding: the model ties the rule on ranking the fraud that matters.** The paired bootstrap (1,000 row resamples, seed 20260929) gives PR-AUC(LightGBM) − PR-AUC(rule) = **+0.0007, 95% CI [−0.0007, +0.0019]**. The CI contains 0, so on TEST there is no measurable PR-AUC gain over `fraud_score`. (On VAL the same difference was +0.0028 [+0.0001, +0.0064], a gain too small to matter.) Logreg is below the rule: −0.0073 [−0.0148, −0.0009].
This backs the architecture: the deterministic rule owns HIGH (card block), and the model is used only where the rule has no signal, to split non-HIGH charges into LOW vs REVIEW. Its higher ROC-AUC (0.84 vs 0.72) comes from ordering that bulk of low-score charges.

**HIGH (card block) on TEST:** `fraud_score > 30` flagged 334 Approved/Declined charges, **334 fraud, 0 legit** (precision 1.000, recall 0.582). Pending/Reversed: 4 HIGH, all fraud. **Wrongful blocks: 0 per 10k charges** (0 legit charges in HIGH out of 663,609 TEST-window charges). For comparison, the old baseline `fraud_score ≥ 30` would have flagged 422 with 88 legit (1.37 per 10k legit).

## 2. Threshold transfer to TEST (t_low chosen on VAL, unchanged)

| | VAL | TEST |
|---|---|---|
| fraud in LOW (missed) / all fraud incl. Pending/Reversed | 29 / 610 = 4.75% [Wilson 95% CI 3.33%, 6.74%] | 29 / 583 = **4.97% [3.49%, 7.05%]** |
| recall outside LOW, all fraud (target 95%) | 95.25% | **95.03%** (meets target) |
| recall outside LOW, Approved/Declined only | 570/599 = 95.16% | 545/574 = **94.95%** |
| fraud in HIGH / rule / REVIEW / LOW | 330 / 6 / 245 / 29 | 338 / 5 / 211 / 29 |

On the locked denominator (all fraud), the threshold holds at 95.03%. On the Approved/Declined-only denominator that `select_low_threshold_given_high` used, TEST is 94.95%, which is 0.05 pp under target (one fraud). The Wilson CI on missed fraud covers 5% in both splits, so we read the threshold as having transferred, with the result sitting right at the target.

## 3. Routing-order split (HIGH → Pending/Reversed rule → LOW/REVIEW)

| | VAL | TEST |
|---|---|---|
| charges (all statuses) | 663,624 | 663,609 |
| HIGH (A/D + P/R) | 330 (325 + 5) | 338 (334 + 4) |
| Pending/Reversed rule | 19,832 | 19,817 |
| REVIEW (human) | 543,754 | 556,915 |
| LOW (auto) | 99,708 | 86,539 |
| LOW share of Approved/Declined | 15.49% | 13.44% |
| **automation rate** = (rule + LOW) / all charges | **18.01%** | **16.03%** |
| human share = (HIGH + REVIEW) / all charges | 81.99% | 83.97% |

On TEST, scores drift slightly upward, so fewer charges fall under the fixed t_low: LOW shrinks from 15.5% to 13.4% of Approved/Declined while missed fraud stays at 29. That is the cost of not re-tuning on TEST.

## 4. Mexico missed-fraud cause (VALIDATION only, no tuning)

| VAL | Mexico | Colombia | Argentina |
|---|---|---|---|
| missed fraud / all fraud | 21/292 = 7.2% [4.8, 10.7] | 4/181 = 2.2% [0.9, 5.5] | 4/137 = 2.9% [1.1, 7.3] |
| fraud by band HIGH / rule / REVIEW / LOW | 155 / 3 / 113 / 21 | 105 / 2 / 70 / 4 | 70 / 1 / 62 / 4 |
| share of fraud with `fraud_score > 30` | 53.1% | 58.0% | 51.1% |
| fraud reaching the model (non-HIGH A/D) that lands in LOW | 21/134 = **15.7%** [10.5, 22.8] | 4/74 = 5.4% [2.1, 13.1] | 4/66 = 6.1% [2.4, 14.6] |
| model score of that fraud, 25th / 50th pct (× t_low) | 1.04 / 1.32 | 1.17 / 1.43 | 1.09 / 1.41 |
| that fraud within 0.5–2× t_low | 59.0% | 56.8% | 54.5% |
| legit A/D charges in LOW | **18.6%** | 10.9% | 14.5% |
| legit model score median (× t_low) | 1.17 | 1.22 | 1.21 |

Supporting detail: all 21 missed Mexico frauds have a `fraud_score` (0.4–27.4, none missing), all are domestic (transaction country Mexico, not cross-border), and all are in USD (all Mexico VAL charges are USD). By channel they split ATM 8, POS 8, App 3, Web 2.

**Cause (en):** Mexico's misses come from the model's LOW cut, not the rule. Mexico fraud has `fraud_score > 30` about as often as elsewhere (53% vs 51–58%), but Mexico charges score lower overall, so the single global t_low sends 18.6% of Mexico legit charges and 15.7% (21/134) of the Mexico fraud the model sees to LOW, vs 10.9–14.5% and 5.4–6.1% in Colombia and Argentina.

**Causa (es):** Los fraudes perdidos en México vienen del corte LOW del modelo, no de la regla. El fraude mexicano tiene `fraud_score > 30` con una frecuencia parecida a la de los otros países (53% vs 51–58%), pero los cargos de México puntúan más bajo en general, así que el único t_low global manda a LOW el 18.6% de los cargos legítimos y el 15.7% (21/134) del fraude que ve el modelo en México, frente a 10.9–14.5% y 5.4–6.1% en Colombia y Argentina.

**Causa (pt):** As fraudes perdidas no México vêm do corte LOW do modelo, não da regra. A fraude mexicana tem `fraud_score > 30` com frequência parecida à dos outros países (53% vs 51–58%), mas as transações do México recebem pontuações mais baixas em geral, então o único t_low global envia para LOW 18,6% das transações legítimas e 15,7% (21/134) da fraude que o modelo vê no México, contra 10,9–14,5% e 5,4–6,1% na Colômbia e na Argentina.

Caveat: the counts are small (21 vs 4 and 4), and the CIs overlap with Argentina's. On TEST (Approved/Declined only, reported, not tuned), missed fraud was Mexico 17/301, Argentina 8/116, Colombia 4/157, and the fairness check raised no FPR-ratio flags. A per-country t_low would be tuning and is out of scope for this submission. It goes on the "what's next" list.

## 5. Pending

- Draft-reply check against the template baseline: follows later today (Oct 3).
- LLM latency and cost per call: measured, see section 6.

## Reproducibility notes

- The ML scripts under `ml/triage/`, `ml/scripts/`, and `ml/evals/` are kept as a record of how the numbers were produced. They read data from local paths outside the repo.
- `out/gold/*.parquet` was missing on the box. It was re-exported read-only from the Data Engineer's `cache/pipeline.duckdb` with `pipeline/export.py`. The train/val/test key hashes all match `splits_manifest.json`.
- Before the single run, `ml/evals/run_test_eval.py` was extended with outputs (a)–(f) and a run marker (`work/TEST_EVAL_STARTED`) that blocks a second run. The extended code was first dry-run on VAL (`/tmp/dry_run_val.py`), where it reproduced every locked VAL number. The original script is in `work/run_test_eval.orig.py`.

## 6. LLM cost and latency (measured, not estimated)

**Where the LLM is used.** I read the app code (`app/reply/draft.py`, `app/cases/engine.py`, `app/api/routes.py` on `feat/judge-features`). The prompt is identical in the local copy @458502c. There is exactly **one** LLM call site: the customer-language reply draft for the human agent, `gpt-4o-mini` with temperature 0, made once each time a handoff is stored. Routing (the rule and LightGBM), the customer-facing replies (templates), PII masking, injection blocking and the draft grounding check are all deterministic, with no LLM. There are no retries: `retry_attempt` is always 0, and on an error the app falls back to the template.

**Price.** gpt-4o-mini Standard: **$0.15 per 1M input tokens, $0.60 per 1M output tokens** (cached input $0.075, not applicable because prompts are about 160 tokens). Source: https://developers.openai.com/api/docs/pricing (the redirect target of platform.openai.com/docs/pricing) and https://platform.openai.com/docs/models/gpt-4o-mini, fetched 2026-10-03 at about 09:25 CST. This matches the app's `app.llm_price` row.

**Per call (gpt-4o-mini, reply_draft)**

| source | n | input tokens mean / median / p95 | output tokens mean / median / p95 | cost per call (mean) | latency p50 / p95 |
|---|---|---|---|---|---|
| logs: `app.audit_llm_call` (deployed app on Cloud Run → OpenAI; QA/test traffic) | 22 | 150.9 / 157 / 166 | 71.0 / 71 / 84.0 | **$0.0000652** | **1,747 / 2,914 ms** |
| direct: box → OpenAI, app's own `_complete()` and prompt, 20 masked VAL charges per band | 80 (80 ok) | 160.1 / 160 / 170 | 59.9 / 63.5 / 74.1 | $0.0000600 | 1,211 / 1,770 ms |

**Calls and cost per case by band** (calls per case from code, confirmed by logs: 22 calls, one per handed-off case; cost uses the direct-measurement mean, n=20 per band, with the logged mean shown alongside)

| band | LLM calls per case | cost per case (direct, n=20) | logged mean (n) | latency p50 / p95 direct |
|---|---|---|---|---|
| HIGH (block confirmed or declined → handoff) | 1 | $0.0000486 | $0.0000693 (4) | 1,120 / 2,382 ms |
| REVIEW (handoff at intake) | 1 | $0.0000644 | $0.0000675 (10) | 1,189 / 1,663 ms |
| Pending/Reversed rule | 0; 1 only if the customer contests | $0 (if contested: $0.0000607) | $0.0000594 (4) | 1,206 / 1,655 ms |
| LOW | 0; 1 only if the customer opens a dispute | $0 (if disputed: $0.0000661) | $0.0000615 (4) | 1,324 / 1,633 ms |
| guardrail block / clarify | 0 | $0 | n/a | n/a |

Takeaways: LLM spend is about **$0.00006 to $0.00007 per handed-off case**, about $65 per million handoffs. It is negligible next to the human handling cost of the same case. Latency matters more than cost: the draft call runs synchronously inside the handoff request (`_store_handoff` → `_record_reply_draft`), so the customer's REVIEW intake and block-confirm responses include about 1.7 s at the median and up to about 2.9 s (logs p95) of OpenAI time.

Update (Oct 3, PR #5 preview `3e1eaf2`, revision 00021-jaj): the draft call now runs after the response, off the customer's request. The AI Engineer reports median REVIEW intake down from 3.2 s to 1.28 s and block-confirm down from 3.75 s to 2.51 s. The console shows "Borrador en preparación…" until the draft is ready. Those latencies are the AI Engineer's measurements, not mine. The latency figures above were measured on the earlier synchronous version; cost per call is unchanged.

Caveats: the logged rows are all QA/test traffic (n=22, with 4 to 10 per band). The escalation rates for LOW and Pending/Reversed (dispute or contest) have not been measured on live traffic yet, so their cost per case = rate × the escalated cost above. Raw data: `work/llm_logged_calls.json`, `work/llm_direct_calls.json`, summary `work/llm_cost_latency.json`, scripts `work/measure_llm.py` and `work/agg_llm.py`.
