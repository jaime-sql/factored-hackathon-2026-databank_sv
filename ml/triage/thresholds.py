"""Documented, re-runnable threshold selection for the 3-band triage.

Bands (on the model's raw score s, a monotone quantity; calibration does not change ranking):
  HIGH   : s >= t_high  -> offer card block (with customer confirmation) + human handoff
  REVIEW : t_low <= s < t_high -> human handoff (review), no block
  LOW    : s <  t_low   -> agent auto-explains / helps identify merchant, may close

Selection (on VALIDATION only):
  t_high = among thresholds with precision >= precision_target and >= `min_high_flags` flagged
           rows, take those achieving the maximum recall, and of those the HIGHEST threshold
           (same recall, fewest false positives / wrongful blocks).
  t_low  = highest threshold such that recall(s >= t_low) >= low_recall_target, i.e. at most
           (1 - low_recall_target) of fraud lands in the LOW (auto) band.
"""

from __future__ import annotations

import numpy as np

from .metrics import Ranked

BANDS = ("low", "review", "high")


def select_thresholds(
    score, y, precision_target: float, low_recall_target: float = 0.95, min_high_flags: int = 50
) -> dict:
    r = Ranked(score, y)
    tp, fp = r.curve()
    P, N = tp[-1], fp[-1]
    flagged = tp + fp
    prec = tp / np.maximum(flagged, 1)
    notes = []

    ok = (prec >= precision_target) & (flagged >= min_high_flags)
    if ok.any():
        idx = np.flatnonzero(ok)
        max_tp = tp[idx].max()
        i_high = int(idx[tp[idx] == max_tp][0])  # first = highest threshold reaching max recall
        high_feasible = True
    else:
        high_feasible = False
        cand = np.flatnonzero(flagged >= min_high_flags)
        i_high = int(cand[np.argmax(prec[cand])])
        notes.append(
            f"HIGH precision target {precision_target:.4f} infeasible; using max-precision threshold "
            f"with >= {min_high_flags} flags (precision {prec[i_high]:.4f})."
        )
    t_high = float(r.thresholds[i_high])

    i_low = int(np.flatnonzero(tp >= low_recall_target * P - 1e-9)[0])
    t_low = float(r.thresholds[i_low])
    low_feasible = True
    if t_low >= t_high:
        low_feasible = False
        notes.append(
            "t_low >= t_high: no review band exists at these targets; setting t_low = t_high."
        )
        t_low = t_high

    return dict(
        t_high=t_high,
        t_low=t_low,
        precision_target=float(precision_target),
        low_recall_target=float(low_recall_target),
        min_high_flags=int(min_high_flags),
        high_feasible=high_feasible,
        low_feasible=low_feasible,
        high_val=dict(
            flagged=int(flagged[i_high]),
            tp=int(tp[i_high]),
            fp=int(fp[i_high]),
            precision=float(prec[i_high]),
            recall=float(tp[i_high] / P),
            fpr=float(fp[i_high] / N),
        ),
        low_val=dict(
            recall_above_low=float(tp[i_low] / P),
            fraud_in_low_band=int(P - tp[i_low]),
            legit_share_in_low_band=float((N - fp[i_low]) / N),
        ),
        notes=notes,
    )


def assign_band(score, t_low: float, t_high: float) -> np.ndarray:
    s = np.nan_to_num(np.asarray(score, dtype="float64"), nan=-np.inf)
    return np.where(s >= t_high, "high", np.where(s >= t_low, "review", "low"))


def band_report(band, y) -> dict:
    band = np.asarray(band)
    y = np.asarray(y).astype(bool)
    n, P, N = len(y), int(y.sum()), int((~y).sum())
    out = {}
    for b in BANDS:
        m = band == b
        out[b] = dict(
            n=int(m.sum()),
            share=float(m.mean()),
            fraud=int((m & y).sum()),
            fraud_rate=float(y[m].mean()) if m.any() else None,
            share_of_all_fraud=float((m & y).sum() / P),
            share_of_legit=float((m & ~y).sum() / N),
        )
    out["false_auto_close_per_10k_tx"] = 1e4 * out["low"]["fraud"] / n
    out["false_auto_close_per_10k_auto_handled"] = (
        1e4 * out["low"]["fraud"] / max(out["low"]["n"], 1)
    )
    return out


def low_band_tradeoff(score, y, targets=(0.99, 0.95, 0.90, 0.85, 0.80, 0.70, 0.60)) -> list:
    """For each recall-above-low target: share of legit / all volume that would be auto-handled
    and fraud missed into the auto band. Used to propose honest alternatives if 0.95 is too costly."""
    r = Ranked(score, y)
    tp, fp = r.curve()
    P, N = tp[-1], fp[-1]
    n = P + N
    out = []
    for t in targets:
        i = int(np.flatnonzero(tp >= t * P - 1e-9)[0])
        out.append(
            dict(
                recall_target=t,
                t_low=float(r.thresholds[i]),
                recall_above_low=float(tp[i] / P),
                fraud_in_low=int(P - tp[i]),
                legit_share_in_low=float((N - fp[i]) / N),
                share_all_in_low=float((n - tp[i] - fp[i]) / n),
                false_auto_close_per_10k_tx=float(1e4 * (P - tp[i]) / n),
            )
        )
    return out


# ---------------------------------------------------------------- v2 banding (team decision 2026-09-29)
HIGH_RULE_THRESHOLD = 30.0  # HIGH = fraud_score > 30 (strict); missing fraud_score is never HIGH


def high_rule_mask(fraud_score) -> np.ndarray:
    fs = np.asarray(fraud_score, dtype="float64")
    return np.nan_to_num(fs, nan=-np.inf) > HIGH_RULE_THRESHOLD


def select_low_threshold_given_high(score, y, high_mask, low_recall_target: float = 0.95) -> dict:
    """Highest raw-score threshold t_low such that fraud kept OUT of LOW (i.e. HIGH, or non-HIGH with
    score >= t_low) is >= low_recall_target of ALL fraud. LOW = non-HIGH and score < t_low."""
    y = np.asarray(y).astype(bool)
    high_mask = np.asarray(high_mask).astype(bool)
    s = np.nan_to_num(np.asarray(score, dtype="float64"), nan=-np.inf)
    P, N = int(y.sum()), int((~y).sum())
    need_outside_high = low_recall_target * P - (high_mask & y).sum()
    nh = ~high_mask
    r = Ranked(s[nh], y[nh])
    tp, fp = r.curve()
    if need_outside_high <= 0:
        t_low, i = float(np.inf), None
    else:
        i = int(np.flatnonzero(tp >= need_outside_high - 1e-9)[0])
        t_low = float(r.thresholds[i])
    kept = (high_mask & y).sum() + (tp[i] if i is not None else 0)
    low = nh & (s < t_low)
    return dict(
        t_low=t_low,
        low_recall_target=float(low_recall_target),
        recall_outside_low=float(kept / P),
        fraud_in_low=int((low & y).sum()),
        legit_share_in_low=float((low & ~y).sum() / N),
        share_all_in_low=float(low.mean()),
        false_auto_close_per_10k_tx=float(1e4 * (low & y).sum() / len(y)),
    )


def assign_band_v2(fraud_score, score, t_low: float) -> np.ndarray:
    s = np.nan_to_num(np.asarray(score, dtype="float64"), nan=-np.inf)
    return np.where(high_rule_mask(fraud_score), "high", np.where(s >= t_low, "review", "low"))


OUT_OF_SCOPE_STATUSES = ("Pending", "Reversed")


def apply_status_rule(band, transaction_status, fraud_score) -> np.ndarray:
    """Team decision 2026-09-29: the HIGH rule (fraud_score > 30) runs BEFORE the Pending/Reversed
    shortcut. Pending/Reversed with fraud_score > 30 -> 'high'; other Pending/Reversed -> 'out_of_scope'
    (deterministic rule-based answer). Other statuses keep their model band."""
    band = np.asarray(band, dtype=object).copy()
    oos = np.isin(np.asarray(transaction_status, dtype=object), OUT_OF_SCOPE_STATUSES)
    hi = high_rule_mask(fraud_score)
    band[oos & hi] = "high"
    band[oos & ~hi] = "out_of_scope"
    return band
