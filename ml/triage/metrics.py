"""Tie-aware ranking metrics with fast weighted bootstrap."""

from __future__ import annotations

import numpy as np


class Ranked:
    """Pre-sorts scores into unique-score groups (descending) so that weighted curves
    (for bootstrap) cost O(n) via bincount."""

    def __init__(self, score, y):
        s = np.asarray(score, dtype="float64")
        s = np.where(np.isnan(s), -np.inf, s)
        self.y = np.asarray(y).astype(bool)
        uniq, inv = np.unique(-s, return_inverse=True)  # ascending of -s => descending s
        self.thresholds = -uniq  # descending
        self.g = inv
        self.G = len(uniq)

    def curve(self, w=None):
        if w is None:
            w = np.ones(len(self.y))
        tp = np.bincount(self.g, weights=w * self.y, minlength=self.G).cumsum()
        fp = np.bincount(self.g, weights=w * (~self.y), minlength=self.G).cumsum()
        return tp, fp  # counts flagged at score >= thresholds[i]


def average_precision(tp, fp):
    P = tp[-1]
    prec = tp / np.maximum(tp + fp, 1e-12)
    dr = np.diff(np.concatenate([[0.0], tp])) / P
    return float(np.sum(dr * prec))


def roc_auc(tp, fp):
    P, N = tp[-1], fp[-1]
    tpr = np.concatenate([[0.0], tp / P])
    fpr = np.concatenate([[0.0], fp / N])
    return float(np.trapezoid(tpr, fpr))


def recall_at_fpr(tp, fp, max_fp_rate):
    """Best recall among thresholds whose FPR <= max_fp_rate."""
    P, N = tp[-1], fp[-1]
    ok = fp <= max_fp_rate * N + 1e-9
    if not ok.any():
        return 0.0, -1
    i = np.flatnonzero(ok)[-1]  # fp is nondecreasing => last ok index has max tp
    return float(tp[i] / P), int(i)


def precision_at_recall(tp, fp, min_recall):
    """Precision at the highest threshold reaching recall >= min_recall."""
    P = tp[-1]
    ok = tp >= min_recall * P - 1e-9
    i = int(np.flatnonzero(ok)[0])
    return float(tp[i] / (tp[i] + fp[i])), i


def confusion_at(score, y, thr):
    s = np.nan_to_num(np.asarray(score, dtype="float64"), nan=-np.inf)
    y = np.asarray(y).astype(bool)
    f = s >= thr
    tp = int((f & y).sum())
    fp = int((f & ~y).sum())
    P = int(y.sum())
    N = int((~y).sum())
    return dict(
        threshold=float(thr),
        flagged=int(f.sum()),
        tp=tp,
        fp=fp,
        precision=tp / max(tp + fp, 1),
        recall=tp / P,
        fpr=fp / N,
        wrongful_flags_per_10k_legit=1e4 * fp / N,
    )


def bootstrap(ranked: dict, rule_flag, y, n=1000, seed=20260929):
    """Row-level bootstrap. For each resample: PR-AUC of each score, and recall of each score
    at the rule's FPR measured on the same resample."""
    rng = np.random.default_rng(seed)
    y = np.asarray(y).astype(bool)
    rule_flag = np.asarray(rule_flag).astype(bool)
    L = len(y)
    out = {k: {"pr_auc": [], "recall_at_rule_fpr": []} for k in ranked}
    for _ in range(n):
        w = np.bincount(rng.integers(0, L, L), minlength=L).astype("float64")
        N = (w * ~y).sum()
        rule_fpr = (w * (rule_flag & ~y)).sum() / N
        for k, r in ranked.items():
            tp, fp = r.curve(w)
            out[k]["pr_auc"].append(average_precision(tp, fp))
            out[k]["recall_at_rule_fpr"].append(recall_at_fpr(tp, fp, rule_fpr)[0])
    res = {}
    for k, d in out.items():
        res[k] = {
            m: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for m, v in d.items()
        }
        res[k]["_diff_vs_first"] = None
    # paired CI of difference vs first key (e.g. model - rule)
    keys = list(ranked)
    for k in keys[1:]:
        for m in ("pr_auc", "recall_at_rule_fpr"):
            diff = np.array(out[k][m]) - np.array(out[keys[0]][m])
            res[k][f"diff_{m}_vs_{keys[0]}_ci"] = [
                float(np.percentile(diff, 2.5)),
                float(np.percentile(diff, 97.5)),
            ]
    return res


def reliability(p, y, n_bins=10):
    """Quantile-binned reliability table + Brier + ECE."""
    p = np.asarray(p, dtype="float64")
    y = np.asarray(y).astype(float)
    order = np.argsort(p, kind="stable")
    bins = np.array_split(order, n_bins)
    rows = []
    ece = 0.0
    for b in bins:
        mp, fr = float(p[b].mean()), float(y[b].mean())
        rows.append(
            dict(
                n=int(len(b)),
                mean_pred=mp,
                frac_pos=fr,
                pos=int(y[b].sum()),
                p_min=float(p[b].min()),
                p_max=float(p[b].max()),
            )
        )
        ece += len(b) / len(p) * abs(mp - fr)
    # tail bins by fixed probability cutoffs (where decisions happen)
    tail = []
    for lo, hi in [(0, 1e-3), (1e-3, 1e-2), (1e-2, 0.1), (0.1, 0.5), (0.5, 1.0001)]:
        m = (p >= lo) & (p < hi)
        if m.sum():
            tail.append(
                dict(
                    bin=f"[{lo},{min(hi, 1)})",
                    n=int(m.sum()),
                    mean_pred=float(p[m].mean()),
                    frac_pos=float(y[m].mean()),
                    pos=int(y[m].sum()),
                )
            )
    return dict(
        brier=float(np.mean((p - y) ** 2)),
        ece_quantile=float(ece),
        mean_pred=float(p.mean()),
        prevalence=float(y.mean()),
        quantile_bins=rows,
        fixed_bins=tail,
    )
