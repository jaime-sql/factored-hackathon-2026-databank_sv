# Threshold simulator: spec for the AI Engineer

Status: DRAFT, 2026-10-02, Data Analytics. The ML Engineer confirmed the `sim_curve.json` schema
below. Still pending: the shipped validation curve and the measured LLM cost per case from the
Oct 2 eval run.

## 1. What it is

A slider on the desk that shows what happens if we move the LOW/REVIEW cut. It is a **static file
shipped with the app** (`static/data/sim_curve.json`). There is **no DB access**: the page loads the
JSON and looks up the nearest cut point. Nothing is computed from live traffic.

- Data label on every tile and on the slider: **"validation set"** (ES "conjunto de validación",
  PT "conjunto de validação"). The test set is never used for the curve.
- Routing order is fixed and the slider never changes it:
  1. **HIGH** = `fraud_score > 30`, fixed rule, checked first. **The slider does not move it.**
  2. **Pending / Reversed** charges get a deterministic rule-based explanation and never reach the model.
  3. Among the rest, the model score splits **LOW** (AI resolves) from **REVIEW** (human handoff).
     **The slider moves only this cut (`t_low`).**
- `n_high` and `n_rule` are constants at the top of the file. Only `n_low` and `n_review` trade places.
  At every point, including the default, `n_high + n_rule + n_low + n_review = n_charges`.

## 2. Starting position

The slider starts at the real 95%-recall threshold from `triage/artifacts/thresholds.json`, key
**`t_low` = 0.000275603870032301** (raw LightGBM score; `score_space` in the same file; selection in
`selection.low_recall_target` = 0.95, `selection.t_low_changed` = false; same value at `val.low.t_low`).
The curve carries that value as top-level `t_low_default` and flags the matching point with
`default: true`. The app selects that point. If no point matches exactly, show the nearest one
and log a warning; the confirmed curve includes the exact `t_low_default` as one of the cut points.

**Locked default point (validation set):** `cut` = `t_low_default` = 0.000275603870032301, automation
**18.01%** (`automation_rate` 0.180132 = (19,832 rule + 99,708 LOW) / 663,624 charges), missed fraud
**29/610** (4.75%, Wilson 95% CI 3.33% to 6.74%). These are the numbers for the tile, the deck and
`docs/analytics.md`; test (16.03% automation, 29/583 missed) is a check only and never feeds the curve.

Cross-check at the start point (ML scope, from `thresholds.json`, not a new figure): fraud in LOW
`val.low.fraud_in_low` = 29 of 610 val fraud, all statuses (599 Approved/Declined + 11 Pending/Reversed;
Wilson 95% CI 3.33% to 6.74%, same as dashboard_spec K4). The missed-fraud tile shows fraud in LOW over all
610, with two separate constant lines under it: fraud caught by HIGH (`fraud_in_high`, including
Pending/Reversed fraud scoring above 30) and fraud explained by the Pending/Reversed rule (`fraud_in_rule`),
both over `n_fraud_total` and read from the curve, never hardcoded. Cross-check: 5 of the 11 Pending/Reversed
fraud route to HIGH, 6 take the rule path. Also
wrongful auto-close `val.low.false_auto_close_per_10k_tx` = 0.45 per 10k charges. The routing-order
curve may use a larger denominator (it includes Pending/Reversed charges); the tiles show whatever the
curve says. **Do not show any automation-rate number from thresholds.json or val_results.json** on the
slider; the automation rate comes only from the ML Engineer's routing-order curve.

## 3. Input: the ML Engineer's curve (confirmed schema)

The ML Engineer creates and pushes `static/data/sim_curve.json`. Field names below are the confirmed
schema (`sim-curve-v1`). `analytics/simulator_cost.py` reads them as-is and does not rename them.

```jsonc
{
  "version": "sim-curve-v1-2026-10-03",
  "split": "validation",
  "model": {"name": "...", "model_sha256": "...", "thresholds_version": "v2-rule-high-2026-09-29"},
  "t_low_default": 0.000275603870032301,
  "n_charges": 663624,
  "n_fraud_total": 610,
  "n_high": 330,                       // constant; the slider does not move HIGH
  "n_rule": 19832,                     // constant; the slider does not move the rule path
  "fraud_in_high": 330,                // constant
  "fraud_in_rule": 6,                  // constant
  "points": [                          // 200 cut points, sorted by cut ascending
    {
      "cut": 0.0,                      // raw LightGBM score cut; one point equals t_low_default
      "default": true,                 // present (true) only on the t_low_default point
      "n_low": 0,
      "n_review": 0,
      "automation_rate": 0.0,          // (n_rule + n_low) / n_charges
      "missed_fraud": {                // fraud in LOW / n_fraud_total, Wilson 95%
        "k": 0, "n": 610, "rate": 0.0, "ci_low": 0.0, "ci_high": 0.0
      },
      "recall_outside_low": 0.0,       // 1 - missed_fraud.rate
      "fraud_in_low_per_10k_low": 0.0, // fraud in LOW per 10,000 LOW charges (null when n_low = 0)
      "cost_per_case": null            // null until analytics/simulator_cost.py fills it
    }
  ]
}
```

Definitions, routing order. Shares are counts over `n_charges`:

- `low = n_low / n_charges`, `review = n_review / n_charges`, `high = n_high / n_charges`,
  `rule = n_rule / n_charges`
- `automation_rate = (n_rule + n_low) / n_charges`
- `missed_fraud.rate = fraud in LOW / n_fraud_total` (`missed_fraud.k / missed_fraud.n`), with a Wilson
  95% interval in `missed_fraud.ci_low` and `missed_fraud.ci_high`
- At the default point, and at every other point, `n_charges = n_high + n_rule + n_low + n_review`

Checks the script runs (it exits non-zero and writes nothing if one fails): `split` is `validation`
and does not mention test; `n_charges`, `n_high` and `n_rule` exist; `points` exists and is
non-empty; for every point the four counts are integers >= 0 and
`n_high + n_rule + n_low + n_review = n_charges` exactly; `automation_rate` matches
`(n_rule + n_low) / n_charges` within 1e-5 (the curve rounds it to 6 decimals).

## 4. Output: enriched curve (same file, fields filled)

`analytics/simulator_cost.py --in-place` fills three per-point fields and two top-level keys and
**never changes the ML Engineer's other fields**. A null or absent `cost_per_case` / `cost_model` is
filled. A non-null value is overwritten only if the existing `cost_model` was written by this
script; otherwise the script stops. All money is USD per charge, one value per human-cost scenario.

```jsonc
{
  "...": "all ML Engineer fields unchanged",
  "cost_model": {
    "generator": "analytics/simulator_cost.py",
    "generated_at_utc": "...",
    "llm_cost_per_case_usd_by_band": {"low": 0.0, "review": 0.0, "high": 0.0, "rule": 0.0},
    "llm_cost_source": {"source": "...", "eval_run_id": "...", "form": "...",
                        "cost_per_call_usd": 0.0, "calls_per_case": {"...": 0}},
    "llm_cost_label": "measured from 22 QA audit rows (live calls)",
    "human_cost_per_resolution_usd": {"low": 1.66, "mid": 3.32, "high": 5.53},
    "human_cost_source": "...",
    "shares": "...", "formula": "...", "fields": "...",
    "assumptions": ["A1 ...", "A2 ...", "A3 ..."]
  },
  "default_point_summary": {           // the t_low_default point, to quote one number
    "point_index": 14, "matched_by": "point flagged default: true",
    "cut": 0.000275603870032301, "t_low_default": 0.000275603870032301,
    "automation_rate": 0.180132, "missed_fraud": {"k": 29, "n": 610, "...": "..."},
    "shares": {"low": 0.0, "review": 0.0, "high": 0.0, "rule": 0.0},
    "cost_per_case": {"low": 0.0, "mid": 0.0, "high": 0.0},
    "human_only": {"low": 1.66, "mid": 3.32, "high": 5.53},
    "net_savings_per_case": {"low": 0.0, "mid": 0.0, "high": 0.0},
    "net_savings_pct_vs_human_only": {"low": 0.0, "mid": 0.0, "high": 0.0},
    "quote_mid": "At the default cut (18.01% automation), expected $X per charge vs ..."
  },
  "points": [
    {
      "...": "ML Engineer fields unchanged",
      "cost_per_case": {"low": 0.0, "mid": 0.0, "high": 0.0},        // expected cost per charge
      "human_only": {"low": 1.66, "mid": 3.32, "high": 5.53},        // human-only cost per charge
      "net_savings_per_case": {"low": 0.0, "mid": 0.0, "high": 0.0}  // human_only - cost_per_case
    }
  ]
}
```

The default point is the one flagged `default: true`; if none, the point whose `cut` equals
`t_low_default`; if none, the nearest cut (`matched_by` says which).

Cost model per charge (counts over `n_charges`, routing order):

| path | cost |
|---|---|
| LOW (AI resolves) | LLM cost (low band) |
| REVIEW (handoff) | LLM cost (review band) + human cost |
| HIGH (block offer + handoff) | LLM cost (high band) + human cost (A1: the agent still runs its LLM turn) |
| Pending/Reversed rule path | LLM cost (rule band), default **0**, no human (A2: template-only, as in dashboard_spec K9) |
| Human-only baseline | human cost for every charge (A3) |

`expected = (llm_low*n_low + llm_review*n_review + llm_high*n_high + llm_rule*n_rule)/n_charges + human*(n_review+n_high)/n_charges`;
`net_savings_per_case = human - expected`.

Human cost per dispute resolution: **$1.66 / $3.32 / $5.53** (low / mid at $12/hr / high), from
`analytics/out/cost_proj_per_resolution.csv` on main (Queja, mean handle time). The LLM cost has no
default: the script fails until the measured value exists. It comes from `--llm-cost-usd X` (flat, same
cost for LOW/REVIEW/HIGH) or `--llm-cost-json eval_cost.json` in one of two forms:

```jsonc
// flat: same LLM cost per case for LOW / REVIEW / HIGH; rule band = --rule-path-llm-cost (default 0)
{"llm_cost_per_case_usd": 0.0, "source": "...", "eval_run_id": "..."}

// per band: llm cost for a band = cost_per_call_usd * calls_per_case[band]
// "rule" is optional; absent -> --rule-path-llm-cost (default 0, A2). Giving both is an error.
{"cost_per_call_usd": 0.0,
 "calls_per_case": {"low": 0, "review": 0, "high": 0, "rule": 0},
 "source": "...", "eval_run_id": "..."}
```

## 5. UI tiles (one set per cut)

Every tile shows the "validation set" tag. Rates use one decimal; money uses 2 decimals (4 for the LLM
cost line). Show `k / n` next to every rate.

| # | Tile | Value from | ES label | PT label |
|---|---|---|---|---|
| T0 | Slider | `cut` | Umbral de riesgo bajo / revisión | Limite entre risco baixo e revisão |
| T0b | Start marker | `default` | Umbral actual (95 % de recall) | Limite atual (95% de recall) |
| T1 | Automation rate | `automation_rate` = `(n_rule + n_low) / n_charges` | Casos que resuelve la IA | Casos que a IA resolve |
| T1b | Subtitle | fixed | Riesgo bajo: la IA explica y puede cerrar | Risco baixo: a IA explica e pode encerrar |
| T2 | Handoff share | `n_review / n_charges` | Pasan a una persona (revisión) | Passam para uma pessoa (revisão) |
| T2b | Fixed counts note | `n_high`, `n_rule` | Riesgo alto y cargos pendientes/revertidos: no cambian con el umbral | Risco alto e cobranças pendentes/estornadas: não mudam com o limite |
| T3 | Missed fraud with CI | `missed_fraud.rate`, `missed_fraud.ci_low`, `missed_fraud.ci_high`, `missed_fraud.k / missed_fraud.n` | Fraude que la IA cerraría (IC 95 %) | Fraude que a IA encerraria (IC 95%) |
| T4 | Wrongful auto-closes, all (includes Pending/Reversed) | `(missed_fraud.k + fraud_in_rule) / n_charges * 10000`, computed by the app (the curve has no such field; `fraud_in_low_per_10k_low` is per 10k LOW auto-closes, not all charges). Captain decision Oct 3: count every wrongful auto-close, LOW plus the 6 rule-explained Pending/Reversed frauds. Default cut on validation: 0.53. | Fraudes cerrados sin revisión humana, por 10k cargos (incluye Pending/Reversed) | Fraudes encerradas sem revisão humana, a cada 10 mil cobranças (inclui Pending/Reversed) |
| T5 | Cost per case (3 scenarios) | `cost_per_case.{low,mid,high}` | Costo por caso (escenario bajo / medio / alto) | Custo por caso (cenário baixo / médio / alto) |
| T5b | Human-only line | `human_only.{low,mid,high}` | Solo personas | Só pessoas |
| T5c | Saving | `net_savings_per_case.{low,mid,high}`; % = `net_savings_per_case / human_only` (precomputed for the default point in `default_point_summary.net_savings_pct_vs_human_only`) | Ahorro por caso frente a solo personas | Economia por caso frente a só pessoas |
| T5d | Cost footnote | `cost_model` | Costo humano por disputa resuelta: US$1,66 / 3,32 / 5,53 (supuesto, salario de US$12/h en el medio). Costo de IA medido en el conjunto de evaluación. PROYECCIÓN. | Custo humano por disputa resolvida: US$ 1,66 / 3,32 / 5,53 (premissa, salário de US$ 12/h no meio). Custo de IA medido no conjunto de avaliação. PROJEÇÃO. |
| T6 | Data tag | fixed | Conjunto de validación (no es tráfico real) | Conjunto de validação (não é tráfego real) |

Wording rules:
- **Never call low risk "seguro"** (or "safe", "sem risco", "sin riesgo"). Use "riesgo bajo" / "risco
  baixo". Missed fraud is never shown as 0 risk; `0 / n` is shown as `0 / n`.
- **Dollar figures follow the page language, not the customer's country.** Amounts stay in USD and are
  never converted to MXN, COP or ARS. Format with the page locale: ES page
  `Intl.NumberFormat('es', {style: 'currency', currency: 'USD'})`, PT page
  `Intl.NumberFormat('pt-BR', {style: 'currency', currency: 'USD'})`. A Mexican customer's case viewed
  on the PT page shows PT formatting.
- Cost tiles carry "PROJECTION" / "PROYECCIÓN" / "PROJEÇÃO".
- Do not show any automation-rate figure until the ML Engineer's routing-order curve is in the file.

## 6. Fairness panel (optional, same page)

`analytics/fairness.py` reproduces the validation scores per customer country (Mexico, Colombia,
Argentina) and checks them against the ML Engineer's artifacts before writing anything. It writes
`static/data/fairness.json` only with `--ship --routing-split <ML Engineer routing-order split>`,
after the routing-order totals match. Fields per country: `n`, `low_share`, `review_share`,
`escalation_ratio_vs_overall`, `missed_fraud` (Wilson 95%), plus a `routing_order` block. Spanish vs
Portuguese is an eval-set comparison, labeled **"on the eval set, PT machine-translated"**; its SQL is
in the script (`EVAL_LANGUAGE_SQL`) and runs only after the Oct 2 eval run fills `eval.case_labels`.

## 7. Files and how to rebuild

| File | Owner | How |
|---|---|---|
| `static/data/sim_curve.json` | ML Engineer (curve), Data Analytics adds cost fields | `python analytics/simulator_cost.py --llm-cost-json <eval cost>.json --in-place` |
| `static/data/fairness.json` | Data Analytics | `python analytics/fairness.py --routing-split <split>.json --ship` |
| `tests/fixtures/test_fixture_sim_curve.json` | Data Analytics | synthetic, tests only, never shipped |

`.gitignore` ignores `data/` and already re-includes `static/data/` (`!static/data/` and
`!static/data/**`). This change does not add `sim_curve.json`, `fairness.json`, or `trust.json`.
