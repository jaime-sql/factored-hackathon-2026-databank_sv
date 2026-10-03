# TEST evaluation (single frozen run)

- test sha256: `fbc11459459e44e9f07aac3d78fa755d33a0aea70f2559f69ee0780d6397390a` (matches manifest), rows 643,788, positives 574
- model sha256 `fb972233981238cc2fb148b27d0f77a1f313c69c6a6c0920b44cee7ca9de6884`; banding v2-rule-high-2026-09-29: HIGH = `fraud_score > 30` (missing -> not HIGH), t_low=0.000275604 (raw score); MLflow run `6b8156af68a440988e2ff36640aca29b`

Rule fraud_score>=30: flagged 422, TP 334, precision 0.7915, recall 0.5819, FPR 0.000137 (1.37/10k legit)

| model | PR-AUC [95% CI] | ROC-AUC | recall @ rule FPR [95% CI] | precision @ rule recall | wrongful flags/10k @ rule FPR |
|---|---|---|---|---|---|
| rule_fraud_score | 0.5833 [0.5468, 0.6229] | 0.7236 | 0.5819 [0.5453, 0.6214] | 1.0000 | 1.37 |
| logreg | 0.5760 [0.5393, 0.6168] | 0.7801 | 0.5697 [0.5350, 0.6120] | 0.1146 | 1.37 |
| lightgbm | 0.5840 [0.5474, 0.6232] | 0.8403 | 0.5819 [0.5453, 0.6214] | 0.8288 | 1.37 |

HIGH rule (fraud_score > 30): flagged 334, TP 334, FP 0, precision 1.0000, recall 0.5819, FPR 0.000000 (0.00/10k legit)

| band | n | share | fraud | fraud rate | share of all fraud | share of legit |
|---|---|---|---|---|---|---|
| low | 86,539 | 13.442% | 29 | 0.0335% | 5.05% | 13.45% |
| review | 556,915 | 86.506% | 211 | 0.0379% | 36.76% | 86.55% |
| high | 334 | 0.052% | 334 | 100.0000% | 58.19% | 0.00% |

False auto-close (fraud in LOW) per 10k transactions: 0.450

Sensitivity only (90% t_low=0.000289932): LOW share 22.62%, fraud in LOW 45, false auto-close/10k 0.699

## Pending / Reversed (HIGH rule runs before the shortcut)

| status | rows | fraud | fraud caught by fraud_score > 30 | legit wrongly flagged | missing fraud_score |
|---|---|---|---|---|---|
| Pending | 13,285 | 6 | 2 | 0 | 2,672 |
| Reversed | 6,536 | 3 | 2 | 0 | 1,301 |
| Pending+Reversed | 19,821 | 9 | 4 | 0 | 3,973 |

## Fairness

**customer_country**

| group | n | pos | fraud rate | HIGH recall | HIGH FPR (ratio) | escalate recall | escalate FPR (ratio) | share low/review/high | small? |
|---|---|---|---|---|---|---|---|---|---|
| Argentina | 127,842 | 116 | 0.091% | 0.612 | 0.00/10k (n/a) | 0.931 | 87.55% (1.01) | 12.44% / 87.50% / 0.056% |  |
| Colombia | 193,618 | 157 | 0.081% | 0.554 | 0.00/10k (n/a) | 0.975 | 90.39% (1.04) | 9.61% / 90.35% / 0.045% |  |
| Mexico | 322,328 | 301 | 0.093% | 0.585 | 0.00/10k (n/a) | 0.944 | 83.85% (0.97) | 16.14% / 83.80% / 0.055% |  |

**customer_segment**

| group | n | pos | fraud rate | HIGH recall | HIGH FPR (ratio) | escalate recall | escalate FPR (ratio) | share low/review/high | small? |
|---|---|---|---|---|---|---|---|---|---|
| Basic | 384,999 | 342 | 0.089% | 0.591 | 0.00/10k (n/a) | 0.950 | 86.50% (1.00) | 13.50% / 86.45% / 0.052% |  |
| Plus | 162,178 | 156 | 0.096% | 0.526 | 0.00/10k (n/a) | 0.955 | 86.65% (1.00) | 13.34% / 86.61% / 0.051% |  |
| Premium | 64,536 | 43 | 0.067% | 0.651 | 0.00/10k (n/a) | 0.907 | 86.62% (1.00) | 13.38% / 86.58% / 0.043% |  |
| Student | 32,075 | 33 | 0.103% | 0.667 | 0.00/10k (n/a) | 0.970 | 86.56% (1.00) | 13.43% / 86.50% / 0.069% |  |

**customer_accent**

| group | n | pos | fraud rate | HIGH recall | HIGH FPR (ratio) | escalate recall | escalate FPR (ratio) | share low/review/high | small? |
|---|---|---|---|---|---|---|---|---|---|
| argentine | 89,809 | 77 | 0.086% | 0.649 | 0.00/10k (n/a) | 0.922 | 87.57% (1.01) | 12.43% / 87.52% / 0.056% |  |
| colombian | 135,110 | 111 | 0.082% | 0.559 | 0.00/10k (n/a) | 0.982 | 90.41% (1.04) | 9.59% / 90.37% / 0.046% |  |
| mexican | 226,722 | 209 | 0.092% | 0.603 | 0.00/10k (n/a) | 0.957 | 83.81% (0.97) | 16.17% / 83.77% / 0.056% |  |
| unknown | 192,147 | 177 | 0.092% | 0.542 | 0.00/10k (n/a) | 0.932 | 86.59% (1.00) | 13.40% / 86.55% / 0.050% |  |

Flags (FPR ratio outside 0.8-1.25):
- none
