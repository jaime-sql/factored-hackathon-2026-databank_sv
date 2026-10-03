"""Shared evaluation/reporting used by the VAL finalization and the (frozen) TEST eval."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import (
    Ranked,
    average_precision,
    bootstrap,
    confusion_at,
    precision_at_recall,
    recall_at_fpr,
    roc_auc,
)
from .thresholds import BANDS


def compare(
    scores: dict, y, rule_flag, n_boot=1000, seed=20260929, high_thresholds: dict | None = None
) -> dict:
    """scores: ordered dict name -> continuous score; first entry must be the rule's fraud_score.
    Operating points: rule (fraud_score>=30), each score at the rule's FPR and at the rule's recall,
    and optionally each model at its frozen HIGH threshold."""
    y = np.asarray(y).astype(bool)
    rule_flag = np.asarray(rule_flag).astype(bool)
    rule = confusion_at(rule_flag.astype(float), y, 1.0)
    ranked = {k: Ranked(v, y) for k, v in scores.items()}
    out = {"rule_operating_point": rule, "models": {}}
    for k, r in ranked.items():
        tp, fp = r.curve()
        rec, i = recall_at_fpr(tp, fp, rule["fpr"])
        thr_fpr = float(r.thresholds[i]) if i >= 0 else None
        prec, j = precision_at_recall(tp, fp, rule["recall"])
        thr_rec = float(r.thresholds[j])
        d = dict(
            pr_auc=average_precision(tp, fp),
            roc_auc=roc_auc(tp, fp),
            at_rule_fpr=confusion_at(scores[k], y, thr_fpr) if thr_fpr is not None else None,
            at_rule_recall=confusion_at(scores[k], y, thr_rec),
        )
        d["recall_at_rule_fpr"] = rec
        d["precision_at_rule_recall"] = prec
        if high_thresholds and k in high_thresholds:
            d["at_high_threshold"] = confusion_at(scores[k], y, high_thresholds[k])
        out["models"][k] = d
    if n_boot:
        out["bootstrap_95ci"] = bootstrap(ranked, rule_flag, y, n=n_boot, seed=seed)
        out["bootstrap_n"] = n_boot
    return out


def fairness(slices: pd.DataFrame, y, band, cols, min_pos=30, lo=0.8, hi=1.25) -> dict:
    """Per-group counts, fraud rate, recall/FPR for HIGH (block) and for escalation (HIGH or REVIEW),
    share in each band; flags groups whose FPR ratio vs overall is outside [lo, hi]."""
    y = np.asarray(y).astype(bool)
    band = np.asarray(band)
    high = band == "high"
    esc = band != "low"

    def stats(m):
        P, N = int((m & y).sum()), int((m & ~y).sum())
        r = dict(
            n=int(m.sum()),
            positives=P,
            fraud_rate=P / max(m.sum(), 1),
            high_recall=(high & m & y).sum() / P if P else None,
            high_fpr=(high & m & ~y).sum() / N if N else None,
            high_fp=int((high & m & ~y).sum()),
            escalate_recall=(esc & m & y).sum() / P if P else None,
            escalate_fpr=(esc & m & ~y).sum() / N if N else None,
            escalate_fp=int((esc & m & ~y).sum()),
        )
        for b in BANDS:
            r[f"share_{b}"] = float((band[m] == b).mean()) if m.any() else None
        r["fraud_in_low"] = int((m & y & (band == "low")).sum())
        return r

    overall = stats(np.ones(len(y), bool))
    res = {"overall": overall, "groups": {}, "flags": []}
    for c in cols:
        vals = slices[c].astype("object").fillna("__NA__").to_numpy()
        res["groups"][c] = {}
        for g in sorted(pd.unique(vals)):
            s = stats(vals == g)
            for key in ("high_fpr", "escalate_fpr"):
                ratio = (s[key] / overall[key]) if (s[key] is not None and overall[key]) else None
                s[f"{key}_ratio"] = ratio
                if ratio is not None and not (lo <= ratio <= hi):
                    res["flags"].append(
                        dict(
                            column=c,
                            group=str(g),
                            metric=key,
                            ratio=ratio,
                            n=s["n"],
                            positives=s["positives"],
                            fp=s["high_fp" if key == "high_fpr" else "escalate_fp"],
                            small_sample=s["positives"] < min_pos
                            or s["high_fp" if key == "high_fpr" else "escalate_fp"] < 20,
                        )
                    )
            s["small_sample"] = s["positives"] < min_pos
            res["groups"][c][str(g)] = s
    return res


def fairness_markdown(f: dict) -> str:
    lines = []
    for c, groups in f["groups"].items():
        lines.append(f"\n**{c}**\n")
        lines.append(
            "| group | n | pos | fraud rate | HIGH recall | HIGH FPR (ratio) | escalate recall | escalate FPR (ratio) | share low/review/high | small? |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for g, s in groups.items():
            fmt = lambda v, p=3: "n/a" if v is None else f"{v:.{p}f}"
            lines.append(
                f"| {g} | {s['n']:,} | {s['positives']} | {s['fraud_rate'] * 100:.3f}% | {fmt(s['high_recall'])} | "
                f"{fmt(s['high_fpr'] * 1e4 if s['high_fpr'] is not None else None, 2)}/10k ({fmt(s['high_fpr_ratio'], 2)}) | "
                f"{fmt(s['escalate_recall'])} | {fmt(s['escalate_fpr'] * 100 if s['escalate_fpr'] is not None else None, 2)}% ({fmt(s['escalate_fpr_ratio'], 2)}) | "
                f"{s['share_low'] * 100:.2f}% / {s['share_review'] * 100:.2f}% / {s['share_high'] * 100:.3f}% | {'yes' if s['small_sample'] else ''} |"
            )
    return "\n".join(lines)
