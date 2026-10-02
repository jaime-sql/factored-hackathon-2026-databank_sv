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
`is_default = true`. The app selects that point. If no point matches exactly, show the nearest one
and log a warning; the confirmed curve includes the exact `t_low_default` as one of the cut points.

Cross-check at the start point (ML scope, from `thresholds.json`, not a new figure): fraud in LOW
`val.low.fraud_in_low` = 29 of 599 val fraud (Wilson 95% CI 3.39% to 6.87%, same as dashboard_spec K4),
wrongful auto-close `val.low.false_auto_close_per_10k_tx` = 0.45 per 10k charges. The routing-order
curve may use a larger denominator (it includes Pending/Reversed charges); the tiles show whatever the
curve says. **Do not show any automation-rate number from thresholds.json or val_results.json** on the
slider; the automation rate comes only from the ML Engineer's routing-order curve.

## 3. Input: the ML Engineer's curve (confirmed schema)

The ML Engineer creates and pushes `static/data/sim_curve.json`. Field names below are the confirmed
schema. `analytics/simulator_cost.py` reads them as-is and does not rename them.

```jsonc
{
  "split": "validation",
  "model_version": "string",
  "t_low_default": 0.000275603870032301,
  "n_charges": 0,
  "n_fraud": 0,
  "n_high": 0,                         // constant; the slider does not move HIGH
  "n_rule": 0,                         // constant; the slider does not move the rule path
  "fraud_in_high": 0,                  // constant
  "fraud_in_rule": 0,                  // constant
  "points": [                          // about 200 cut points, sorted by t_low ascending
    {
      "t_low": 0.0,                    // raw LightGBM score cut; one point equals t_low_default
      "is_default": false,             // true only for the t_low_default point
      "n_low": 0,
      "n_review": 0,
      "automation_rate": 0.0,          // (n_rule + n_low) / n_charges
      "missed_fraud_n": 0,             // fraud in LOW
      "missed_fraud_rate": 0.0,        // missed_fraud_n / n_fraud
      "missed_fraud_ci_lo": 0.0,       // Wilson 95%
      "missed_fraud_ci_hi": 0.0,       // Wilson 95%
      "wrongful_autoclose_per_10k": 0.0   // missed_fraud_n / n_charges * 10000
    }
  ]
}
```

Definitions, routing order:

- `automation_rate = (n_rule + n_low) / n_charges`
- `missed_fraud_rate = fraud in LOW / n_fraud` (`missed_fraud_n / n_fraud`), with a Wilson 95% interval
  in `missed_fraud_ci_lo` and `missed_fraud_ci_hi`
- `wrongful_autoclose_per_10k = fraud in LOW / n_charges * 10000`
- At the default point, and at every other point, `n_charges = n_high + n_rule + n_low + n_review`

Checks the script runs (it exits non-zero and writes nothing if one fails): `split` is `validation`;
`points` exists, is non-empty, and is sorted by `t_low`; exactly one point has `is_default = true`
and its `t_low` equals `t_low_default`; for every point
`n_high + n_rule + n_low + n_review = n_charges`; the three rate formulas above hold (tolerance 1e-6).

## 4. Output: enriched curve (same file, fields added)

`analytics/simulator_cost.py --in-place` adds two keys and **never changes the ML Engineer's fields**:

```jsonc
{
  "...": "all ML Engineer fields unchanged",
  "cost_model": {
    "generator": "analytics/simulator_cost.py",
    "generated_at_utc": "...",
    "llm_cost_per_case_usd": 0.0,            // measured, Oct 2 eval run; required, no default
    "llm_cost_source": {"source": "...", "eval_run_id": "..."},
    "llm_cost_label": "measured on the eval set (Oct 2 eval run)",
    "rule_path_llm_cost_usd": 0.0,
    "human_cost_per_resolution_usd": {"low": 1.66, "mid": 3.32, "high": 5.53},
    "human_cost_source": "...",
    "formula": "...",
    "assumptions": ["A1 ...", "A2 ...", "A3 ..."]
  },
  "points": [
    {
      "...": "ML Engineer fields unchanged",
      "cost_per_case": {
        "low":  {"human_cost_per_resolution_usd": 1.66, "expected_cost_per_case_usd": 0.0,
                 "human_only_cost_per_case_usd": 1.66, "saving_per_case_usd": 0.0,
                 "saving_pct_vs_human_only": 0.0},
        "mid":  {"...": "same fields at 3.32"},
        "high": {"...": "same fields at 5.53"}
      }
    }
  ]
}
```

Cost model per charge (counts over `n_charges`, routing order):

| path | cost |
|---|---|
| LOW (AI resolves) | LLM cost |
| REVIEW (handoff) | LLM cost + human cost |
| HIGH (block offer + handoff) | LLM cost + human cost (A1: the agent still runs its LLM turn) |
| Pending/Reversed rule path | `rule_path_llm_cost_usd`, default **0**, no human (A2: template-only, as in dashboard_spec K9) |
| Human-only baseline | human cost for every charge (A3) |

`expected = llm*(n_low+n_review+n_high)/n_charges + rule_llm*n_rule/n_charges + human*(n_review+n_high)/n_charges`.

Human cost per dispute resolution: **$1.66 / $3.32 / $5.53** (low / mid at $12/hr / high), from
`analytics/out/cost_proj_per_resolution.csv` on main (Queja, mean handle time). The LLM cost per case
is a CLI arg or a JSON file and has no default: the script fails until the measured value exists.

## 5. UI tiles (one set per cut)

Every tile shows the "validation set" tag. Rates use one decimal; money uses 2 decimals (4 for the LLM
cost line). Show `k / n` next to every rate.

| # | Tile | Value from | ES label | PT label |
|---|---|---|---|---|
| T0 | Slider | `t_low` | Umbral de riesgo bajo / revisión | Limite entre risco baixo e revisão |
| T0b | Start marker | `is_default` | Umbral actual (95 % de recall) | Limite atual (95% de recall) |
| T1 | Automation rate | `automation_rate` = `(n_rule + n_low) / n_charges` | Casos que resuelve la IA | Casos que a IA resolve |
| T1b | Subtitle | fixed | Riesgo bajo: la IA explica y puede cerrar | Risco baixo: a IA explica e pode encerrar |
| T2 | Handoff share | `n_review / n_charges` | Pasan a una persona (revisión) | Passam para uma pessoa (revisão) |
| T2b | Fixed counts note | `n_high`, `n_rule` | Riesgo alto y cargos pendientes/revertidos: no cambian con el umbral | Risco alto e cobranças pendentes/estornadas: não mudam com o limite |
| T3 | Missed fraud with CI | `missed_fraud_rate`, `missed_fraud_ci_lo`, `missed_fraud_ci_hi`, `missed_fraud_n / n_fraud` | Fraude que la IA cerraría (IC 95 %) | Fraude que a IA encerraria (IC 95%) |
| T4 | Wrongful auto-closes | `wrongful_autoclose_per_10k` | Cierres automáticos erróneos por cada 10 000 cargos | Encerramentos automáticos indevidos a cada 10.000 cobranças |
| T5 | Cost per case (3 scenarios) | `cost_per_case.{low,mid,high}.expected_cost_per_case_usd` | Costo por caso (escenario bajo / medio / alto) | Custo por caso (cenário baixo / médio / alto) |
| T5b | Human-only line | `human_only_cost_per_case_usd` | Solo personas | Só pessoas |
| T5c | Saving | `saving_per_case_usd`, `saving_pct_vs_human_only` | Ahorro por caso frente a solo personas | Economia por caso frente a só pessoas |
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
