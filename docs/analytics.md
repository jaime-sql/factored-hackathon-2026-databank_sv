# Analytics

DRAFT, 2026-09-29. Owner: Data Analytics.
Every number here comes from the script outputs listed under each section (`run.log`, `out/*.csv`) or from
`/workspace/hackathon-data/data-quality.md`. Numbers are tagged:

- **[FACT]** measured in the supplied (historical, largely synthetic) data;
- **[ASSUMPTION]** chosen by the team, not in the data;
- **[PROJECTION]** facts combined with assumptions; not a measured saving;
- **[TBD]** waiting on the ML Engineer's eval run (Oct 2).

## 1. Purpose

Show, with the supplied data, why transaction-level dispute intake ("I don't recognize this charge") is worth
automating, what a human currently costs for it, and how the agent will be measured. The agent handles one charge per
case: HIGH (`fraud_score > 30`) is checked first for every status; otherwise Pending and Reversed charges get fixed
rule-based explanations; remaining Approved/Declined charges go through fraud triage and hand off to a human when needed.

## 2. Data sources and lineage

| step | artifact | owner |
|---|---|---|
| Official dataset (S3, organizer-provided, CSV, hive-partitioned) | `/workspace/hackathon-data/raw` | organizers |
| Profiling + data-quality report | `/workspace/hackathon-data/data-quality.md` (`profile.py`) | Data Engineer |
| Local DuckDB copy | `/workspace/hackathon-data/cache/bank.duckdb` | Data Engineer |
| Demand metrics (read-only on the DuckDB) | `demand_metrics.py` → `out/tx_*.csv`, `out/cp_*.csv`, `out/res_*.csv`, `out/cost_*.csv`, `demand_metrics.sql`, `run.log`, charts 01–03 | Data Analytics |
| Cost projection (read-only on the DuckDB) | `cost_projection.py` → `out/cost_proj_*.csv`, chart 04 | Data Analytics |
| App + audit log (live/eval) | Supabase Postgres, project `factored-hackathon-2026`, RLS on every table | AI Engineer |

Tables used: `transactions`, `customers` (country and segment via `customer_id`; 0 orphans), `complaints`,
`call_center_interactions`. Country and segment are the customer's home country/segment, not the transaction country.
The data window is 2023-06-17 to 2026-06-18; the first and last months are partial.

## 3. Demand analysis and why this workflow

Charts: [01_case_mix.png](../analytics/charts/01_case_mix.png), [02_complaint_trend.png](../analytics/charts/02_complaint_trend.png), [03_resolution_days.png](../analytics/charts/03_resolution_days.png), [05_dispute_case_mix.png](../analytics/charts/05_dispute_case_mix.png).

**Transactions (case mix)** [FACT] (`out/tx_overall.csv`, `out/tx_case_mix.csv`)

| bucket (mutually exclusive, in this order) | transactions | share |
|---|---:|---:|
| HIGH (`fraud_score > 30`, any status) | 2,373 | 0.054% |
| Pending (otherwise) | 88,297 | 1.995% |
| Reversed (otherwise) | 44,732 | 1.011% |
| Other (Approved/Declined, score <= 30 or null) | 4,289,606 | 96.940% |
| **Total** | **4,425,008** | |

- The HIGH bucket contains 2,373 full-table transactions; `fraud_score` is null on 20% of rows
  (3,539,851 of 4,425,008 scored). [FACT]
- The current baseline is `fraud_score > 30`; the held-out TEST split was not rerun or changed in this update. [FACT]

**Complaints** [FACT] (`out/cp_overall.csv`, `out/cp_categories.csv`)

- 67,095 complaints. Disputes (`category = 'Transactions'`): **13,580 (20.2%)**; 12,297 of them have subcategory
  'Cargo no reconocido', the other 1,283 have no subcategory. Broad definition (Transactions + Fees 'Cobro indebido'):
  27,133 (40.4%).
- The five categories are almost equal in size (Transactions 13,580, Fees 13,553, Technical 13,407, Branch 13,361,
  Service 13,194), so volume alone does not single out disputes.
- Monthly dispute volume is flat: mean **377.5 per full month** (35 full months, Jul 2023–May 2026, range 335–424)
  (`out/cost_proj_dispute_volume_by_month.csv`).
- Half of dispute complaints arrive by Call Center (6,849 of 13,580) (`out/cp_by_channel_group.csv`).

**Resolution and SLA** [FACT, but see §6] (`out/res_overall.csv`, `out/res_by_cat_group.csv`, `out/res_sla_vs_days.csv`)

- Only 25.1% of complaints (16,826 of 67,095) have a final status (Resolved/Closed/Rejected); 25.45% for disputes.
- Median time to resolution for disputes: **15 days** (p90 27 days); all complaints: 16 days (p90 28). Based on the
  15,487 complaints with both timestamps.
- `sla_breached` is true on about 20% of complaints in every cut (20.11% overall; 19.75–20.41% by country), and breached
  cases do not take longer (median 15.0 d breached vs 16.0 d not breached). There is no SLA target column.

**Human handle time** [FACT] (`out/cost_proj_inputs_handle_time.csv`, `out/cost_callcenter_handle_time.csv`)

| call-center reason | interactions | mean handle time | resolved on contact |
|---|---|---|---|
| Queja (complaint) | 117,021 | 434.6 s | 43.6% |
| Transaccional | 240,056 | 220.8 s | 91.5% |

Transaccional is the largest call-center reason (240,056 of 686,296 interactions). Resolution rates are computed on
contacts that have a duration (voice/video); chat and email have no duration.

**Uniformity across slices** [FACT] (`out/tx_by_country.csv`, `out/tx_by_segment.csv`, `out/cp_by_country.csv`,
`out/cp_by_segment.csv`, `out/res_by_segment.csv`): Pending share 1.99–2.02% by country; dispute share of complaints
20.21–20.25% by country and 19.90–20.62% by segment; final-status share 24.73–25.27% by segment; Transaccional handle
time 217.5–222.8 s across all country x segment cells. The data shows no historical disparity, and also little signal.

**Why this workflow**

1. It is a frequent, well-defined request: disputes are one of the five near-equal complaint categories and sit on top of
   the largest call-center reason (Transaccional).
2. A human dispute contact is expensive: a Queja takes about twice as long as a Transaccional contact and less than half
   are resolved on the contact (see §4).
3. Part of the answer is deterministic and reliable in the data: Pending and Reversed statuses are clean (3.0% of
   transactions together), so those cases can be explained by rules, not by an LLM.
4. The risky part has a usable signal: `fraud_score > 30` is the current HIGH rule (all 325 current VAL HIGH cases
   are fraud, with zero legitimate flags), which gives a baseline for triage and a clear handoff rule.
5. It fits the brief's required paths: normal (pending/reversed explanation), ambiguous/unsupported (`other`), and human
   intervention (triage handoff).

What the data does NOT show: which share of real dispute complaints are about Pending, Reversed or fraudulent charges,
because complaints cannot be linked to transactions (§6).

## 4. Cost model

Source: `cost_projection.py` (assumptions block at the top), outputs `out/cost_proj_*.csv`, chart
[04_cost_projection.png](../analytics/charts/04_cost_projection.png).

**Formulas**
- cost per contact = handle time (s) / 3600 x loaded cost per hour
- cost per resolution = cost per contact / resolution rate (escalated contacts stay in the denominator)
- monthly human cost = disputes per month x cost per contact (Queja)

**Assumptions** [ASSUMPTION]
- A1. Fully loaded agent cost: **$6 / $12 / $20 per hour** (low / mid / high, LatAm contact center).
- A2. Each dispute costs one Queja-type contact.
- A3. Mean handle time is used (median results are within 1%, see `out/cost_proj_per_resolution.csv`).
- A4. LLM cost per case: **[TBD]** from the ML Engineer's run (Oct 2); set `LLM_COST_PER_CASE_USD` in the script.

**Results** [PROJECTION, from `out/cost_proj_per_resolution.csv`, `out/cost_proj_monthly_disputes.csv`]

| | low $6/h | mid $12/h | high $20/h |
|---|---|---|---|
| Queja cost per contact | $0.72 | $1.45 | $2.41 |
| **Queja cost per dispute resolution** | **$1.66** | **$3.32** | **$5.53** |
| Transaccional cost per resolution (reference) | $0.40 | $0.80 | $1.34 |
| Monthly human cost at 377.5 disputes/month, per contact | $273 | $547 | $911 |
| Same, per resolution basis | $627 | $1,253 | $2,088 |
| Scaled to 10,000 disputes/month, per resolution basis | $16.6k | $33.2k | $55.3k |
| Scaled to 10,000 disputes/month, per contact basis | $7.2k | $14.5k | $24.1k |

- The 10,000/month rows are simple arithmetic (10,000 x the unit cost above); they are not in the script outputs.
  10,000/month is an illustrative bank size, not a figure from the data. At the dataset's own volume the amounts are small.
- The per-resolution basis assumes every dispute needs contacts until it is resolved on a contact; the per-contact basis
  counts one contact per dispute. The script's sensitivity table uses the per-contact basis; treat per resolution as the upper figure.
- Sensitivity (`out/cost_proj_sensitivity_automation.csv`, per contact basis, 377.5 disputes/month): automating 25 / 50 / 75%
  of disputes avoids $68 / $137 / $205 per month (low) up to $228 / $456 / $684 (high), before LLM cost.
  **Net savings = TBD** until LLM cost per case is known.
- Only **safe** automated resolutions count toward cost avoided. Wrong auto-closes are unsafe outcomes, not savings.

**Placeholders to fill after Oct 2** [TBD]
- LLM cost per case (by case type): `TBD`
- Safe-auto projection input (in-scope eval cases, derived from fidelity plus safety labels): `TBD` (k / n)
- Wrong auto-close rate: `TBD` (k / n)
- Net monthly savings (low / mid / high): `TBD`

## 5. KPIs

Full definitions, formulas, audit-log fields, SQL and the required audit-log schema are in
[`dashboard_spec.md`](dashboard_spec.md). Offline label-based KPIs join `eval.case_labels` to
`app.audit_current` on `case_id` and filter to one chosen `eval_run_id`; `eval.transaction_labels` is retained only for
transaction population/source analyses.

**Offline eval group A — agent fidelity** (broken down by `case_source`; `sample` is the headline, `red_team` is separate,
and `pt_translated` is labeled machine-translated):

- `outcome_correct` rate (`k / n`, percentage), meaning whether the agent followed the case's rule or policy band.

**Offline eval group B — triage safety against `is_fraud`** (same source breakdown):

- wrong auto-close count, rate as a percentage, and rate per 10,000 labeled cases;
- wrongful-block count;
- HARD ZERO: high-score fraud cases (`fraud_score > 30`) auto-resolved, joined through `case_labels.transaction_key` to
  `public.transactions`; any non-zero count is a red alert;
- fraud auto-resolve rate: auto-resolved fraud cases / all fraud cases, per eval run and `case_source`, with its own 95%
  Wilson CI. The val reference is 29/599 = 4.8414023372%, with CI **[3.3917781042%, 6.8665506679%]**; flag only when
  the run CI is entirely above that interval;
- PII-leak count;
- injection success out of attempts (`k / n`, percentage);
- groundedness p50, mean, and share below 0.8.

Operational/live KPIs must exclude eval traffic with `eval_run_id IS NULL` and display the label **"fraud-enriched demo
sample"**. They must never be mixed with an eval-run result. Supporting KPIs are case volume, automation attempted rate,
handoff rate and reasons, containment, time to resolution, cost, latency, guardrail events and reliability. Projection:
human cost avoided (labeled PROJECTION). Fairness slices use the same fidelity/safety metrics by country, segment,
language and `case_source`, with a disparity flag at > 5 points between groups with n >= 30 (heuristic).

## 6. Data limitations

- **Largely synthetic data.** Descriptions and resolutions are templated (5 distinct texts each); resolution days are
  spread almost evenly over 1–30 days (`out/res_days_hist.csv`); the SLA flag is ~20% everywhere and unrelated to
  resolution time; outcome rates are uniform across categories, countries and segments. Historical resolution times
  and SLA are context, not a baseline to beat.
- **No complaint → transaction link.** Complaints have no transaction_id, `affected_product_id` never belongs to the
  complaining customer, and `origin_interaction_id` is 100% null. We cannot measure which disputes were about Pending,
  Reversed or fraudulent charges. Eval cases therefore have to be constructed per transaction.
- **Few and weak labels.** 3,456 disputes have a final status; 125 are Rejected. `is_fraud` is rare (4,316 of 4,425,008).
  Transaction ground-truth `is_fraud` for transaction population/source analysis lives in `eval.transaction_labels` keyed
  by `transaction_key`; case-level answer and safety labels live in `eval.case_labels` keyed by `case_id`. The agent and
  read-only console never read them, and label-based KPIs are computed only in the offline analytics/eval report.
- **No duplicate charges** in the data (0 strict candidates). The duplicate case type uses a synthetic fixture
  (300 cases: 181 true duplicates, 119 legitimate repeats), flagged `is_synthetic`.
- **No Portuguese.** All 171,321 call transcripts are Spanish (`detected_language = es`). Portuguese (`pt`) results come
  only from machine-translated test cases; report them as their own slice and never present them as coming from the real data.
- **Accent** is null for about 30% of customers and interactions; accent slices will be small.
- **Other quirks:** transaction timestamps carry a fixed +6 h shift vs process_date; `transaction_country` has mixed
  labels (México/Mexico, plus USA, Spain, Brazil); no MXN transaction currency; complaint currency is independent of
  customer country; row counts differ from the data dictionary (e.g. transactions 4,425,008 vs 5,000,000);
  handle time exists only for voice/video contacts.
- **Cost model** depends on assumed wage rates and on one-contact-per-dispute; LLM cost is not yet measured.

## 7. Reproducibility

```bash
cd /workspace/hack-analytics
# Python 3.13, duckdb 1.5.6, pandas 3.0.6, matplotlib 3.11.2 (in .venv)
.venv/bin/python demand_metrics.py > run.log   # out/tx_*, cp_*, res_*, cost_* CSVs, demand_metrics.sql, charts 01-03
.venv/bin/python cost_projection.py            # out/cost_proj_*.csv, generated chart 04_cost_projection.png
```

- Both scripts open `/workspace/hackathon-data/cache/bank.duckdb` read-only and are deterministic.
- All SQL used by `demand_metrics.py` is written to `demand_metrics.sql`.
- To update the cost model, edit only the ASSUMPTIONS block at the top of `cost_projection.py` (e.g. set
  `LLM_COST_PER_CASE_USD` after Oct 2) and re-run; the sensitivity table then fills the LLM cost and net savings columns.
- `run.log` holds only the `demand_metrics.py` console output; the cost projection's results are in `out/cost_proj_*.csv`.
