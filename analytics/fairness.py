"""Fairness of the LOW/REVIEW triage cut by customer country, on the VALIDATION set.

Writes static/data/fairness.json (static file shipped with the app; no DB access at runtime).

What it computes, per customer country (Mexico, Colombia, Argentina) and overall:
  - n, LOW (AI auto-resolve) share, REVIEW (human handoff) share, HIGH share
  - escalation ratio vs overall = REVIEW share in the group / REVIEW share overall
  - legit escalation ratio = share of legit charges sent to a human (REVIEW or HIGH) in the group /
    the same share overall (the ML Engineer's `escalate_fpr_ratio`; reproduced as a check)
  - missed fraud = fraud that lands in LOW / all fraud in the group, with a Wilson 95% interval
  - the same shares in full routing order (HIGH first, then the Pending/Reversed rule path, then the
    model), where the denominator also includes the rule-path charges.

Faithfulness gates (the script refuses to write anything if one fails):
  1. sha256 of model.txt == thresholds.json["model_sha256"]
  2. sha256 of the sorted VAL transaction keys == thresholds.json["data_hashes"]["val"]
  3. reproduced band counts == thresholds.json["val"]["band_counts"], and fraud in LOW ==
     thresholds.json["val"]["low"]["fraud_in_low"]
  4. per-country n / positives / fraud_in_low == val_results.json
     ["banding_v2"]["fairness"]["groups"]["customer_country"]
  5. Pending/Reversed VAL rows / fraud / HIGH rows ==
     val_results.json["pending_reversed_high"]["val"]
The TEST split is never read: every query filters split = 'val' or the VAL time window.

Inputs (not in this repo):
  PIPELINE_DUCKDB_PATH  default /workspace/hackathon-data/cache/pipeline.duckdb
                        (tables gold.fraud_features, gold.transactions_masked)
  HACK_ML_ARTIFACTS     default /workspace/hack-ml/artifacts
                        (model.txt, feature_list.json, category_mappings.json, thresholds.json,
                        val_results.json)
  SPLITS_MANIFEST_PATH  default /workspace/hackathon-data/splits_manifest.json

Run:
  python analytics/fairness.py                       # writes analytics/out/fairness.json (local)
  python analytics/fairness.py --routing-split ROUTING_SPLIT.json --ship
                                                     # writes static/data/fairness.json
Shipping is refused unless the ML Engineer's routing-order validation split (--routing-split) is
given and its totals match this reproduction (gate 6). Until that split lands, the team rule is that
no overall automation-rate figure goes into new material, so the shipped file waits for it.
Accepted routing-split shapes (keys at top level or under "totals"; confirm with the ML Engineer):
  n_charges, n_high, n_rule, n_low, n_review   (counts on the VAL set in routing order)
Needs duckdb, pandas, pyarrow, lightgbm==4.7.0, pytz (imported lazily so the helpers stay testable).

Spanish vs Portuguese is NOT computed here from data: it comes from the eval cases after the Oct 2
eval run. The SQL is in EVAL_LANGUAGE_SQL below ("on the eval set, PT machine-translated"); it is
not executed by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHIP_OUT = REPO / "static" / "data" / "fairness.json"
DEFAULT_OUT = REPO / "analytics" / "out" / "fairness.json"  # local only, do not commit
COUNTRIES = ("Mexico", "Colombia", "Argentina")
Z95 = 1.959963984540054
HIGH_VALUE = 30.0  # read from thresholds.json["high_rule"]["value"] and asserted at run time

# Offline eval KPI: ES vs PT, on the eval set, PT machine-translated. Not executed by this script.
# Run it in the offline eval report after the Oct 2 eval run fills eval.case_labels.
EVAL_LANGUAGE_SQL = """
-- On the eval set (deliberately enriched; PT cases are machine-translated). Not real traffic.
WITH labeled AS (
  SELECT a.case_id, a.language, a.country, a.decision, a.case_type,
         l.eval_run_id, l.case_source, l.is_fraud, l.expected_decision, l.outcome_correct
  FROM app.audit_current AS a
  JOIN eval.case_labels AS l ON l.case_id = a.case_id
  WHERE a.eval_run_id = $1
    AND l.eval_run_id = $1
    AND a.case_type = 'triage'
)
SELECT language,
       count(*) AS n,
       count(*) FILTER (WHERE decision = 'auto_resolved') AS auto_resolved_k,
       count(*) FILTER (WHERE decision = 'handoff') AS handoff_k,
       count(*) FILTER (WHERE is_fraud) AS fraud_n,
       count(*) FILTER (WHERE is_fraud AND decision = 'auto_resolved') AS fraud_auto_resolved_k,
       count(*) FILTER (WHERE outcome_correct) AS outcome_correct_k,
       'on the eval set, PT machine-translated'::text AS label
FROM labeled
GROUP BY language
ORDER BY language;
"""


class GateError(RuntimeError):
    """A faithfulness gate failed: the reproduction does not match the ML Engineer's artifacts."""


def wilson(k: int, n: int, z: float = Z95) -> dict:
    """Wilson score interval for k successes out of n. Returns rate and bounds (None if n == 0)."""
    if n <= 0:
        return {"k": k, "n": n, "rate": None, "ci95_low": None, "ci95_high": None}
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return {
        "k": k,
        "n": n,
        "rate": p,
        "ci95_low": max(0.0, centre - half),
        "ci95_high": min(1.0, centre + half),
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sorted_key_hash(keys) -> str:
    k = sorted(map(str, keys))
    return hashlib.sha256(("\n".join(k) + "\n").encode()).hexdigest()


def _require(path: Path, what: str) -> Path:
    if not path.exists():
        sys.exit(f"MISSING INPUT: {what} not found at {path}")
    return path


def group_stats(band, y, mask) -> dict:
    """Model-scope stats for the rows in mask. band in {'high','review','low'}; y is bool."""
    n = int(mask.sum())
    b = band[mask]
    yy = y[mask]
    pos = int(yy.sum())
    legit = n - pos
    low = int((b == "low").sum())
    review = int((b == "review").sum())
    high = int((b == "high").sum())
    fraud_in_low = int(((b == "low") & yy).sum())
    legit_escalated = int(((b != "low") & ~yy).sum())
    return {
        "n": n,
        "positives": pos,
        "low_n": low,
        "review_n": review,
        "high_n": high,
        "low_share": low / n if n else None,
        "review_share": review / n if n else None,
        "high_share": high / n if n else None,
        "legit_escalated_share": legit_escalated / legit if legit else None,
        "missed_fraud": wilson(fraud_in_low, pos),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=None, help="override output path")
    ap.add_argument("--routing-split", default=None, help="ML Engineer routing-order split JSON")
    ap.add_argument("--ship", action="store_true", help="write static/data/fairness.json")
    args = ap.parse_args(argv)
    if args.ship and not args.routing_split:
        sys.exit(
            "REFUSING TO SHIP: --ship needs --routing-split (the ML Engineer's Oct 2 routing-order "
            "validation split) so the overall shares are cross-checked before they are published."
        )
    out_path = Path(args.out) if args.out else (SHIP_OUT if args.ship else DEFAULT_OUT)
    if out_path.resolve() == SHIP_OUT.resolve() and not args.routing_split:
        sys.exit("REFUSING TO WRITE static/data/fairness.json without --routing-split.")

    art = Path(os.environ.get("HACK_ML_ARTIFACTS", "/workspace/hack-ml/artifacts"))
    db = Path(
        os.environ.get("PIPELINE_DUCKDB_PATH", "/workspace/hackathon-data/cache/pipeline.duckdb")
    )
    manifest_p = Path(
        os.environ.get("SPLITS_MANIFEST_PATH", "/workspace/hackathon-data/splits_manifest.json")
    )
    for name in (
        "model.txt",
        "feature_list.json",
        "category_mappings.json",
        "thresholds.json",
        "val_results.json",
    ):
        _require(art / name, f"ML artifact {name}")
    _require(db, "pipeline DuckDB (gold.fraud_features)")
    _require(manifest_p, "splits manifest")

    import duckdb
    import lightgbm as lgb
    import numpy as np
    import pandas as pd

    T = json.loads((art / "thresholds.json").read_text())
    R = json.loads((art / "val_results.json").read_text())
    feats = json.loads((art / "feature_list.json").read_text())
    cat_maps = json.loads((art / "category_mappings.json").read_text())
    manifest = json.loads(manifest_p.read_text())
    rule = T["high_rule"]
    if not (rule["op"] == ">" and rule["missing"] == "not HIGH" and rule["value"] == HIGH_VALUE):
        raise GateError(f"unexpected HIGH rule in thresholds.json: {rule}")
    t_low = float(T["t_low"])

    # Gate 1: model file
    model_sha = sha256_file(art / "model.txt")
    if model_sha != T["model_sha256"]:
        raise GateError(f"model.txt sha256 {model_sha} != thresholds.json {T['model_sha256']}")

    con = duckdb.connect(str(db), read_only=True)
    cols = list(
        dict.fromkeys(["transaction_key", "is_fraud", "customer_country"] + feats["features"])
    )
    df = con.execute(f"SELECT {', '.join(cols)} FROM gold.fraud_features WHERE split = 'val'").df()

    # Gate 2: exact VAL population
    val_hash = sorted_key_hash(df["transaction_key"])
    if val_hash != T["data_hashes"]["val"]:
        raise GateError(f"VAL key hash {val_hash} != thresholds.json {T['data_hashes']['val']}")

    cat = set(feats["categorical"])
    X = {}
    for c in feats["features"]:
        if c in cat:
            s = df[c].astype("object").where(df[c].notna(), None)
            X[c] = pd.Categorical(s, categories=cat_maps[c])
        else:
            X[c] = pd.to_numeric(df[c].astype("object"), errors="coerce").astype("float32")
    booster = lgb.Booster(model_file=str(art / "model.txt"))
    raw = booster.predict(pd.DataFrame(X, index=df.index))
    fs = pd.to_numeric(df["fraud_score"].astype("object"), errors="coerce").to_numpy("float64")
    hi = np.nan_to_num(fs, nan=-np.inf) > HIGH_VALUE
    s = np.nan_to_num(np.asarray(raw, dtype="float64"), nan=-np.inf)
    band = np.where(hi, "high", np.where(s >= t_low, "review", "low")).astype(object)
    y = df["is_fraud"].astype(bool).to_numpy()
    country = df["customer_country"].astype("object").fillna("__NA__").to_numpy()

    # Gate 3: band counts and fraud in LOW
    got = {b: int((band == b).sum()) for b in ("high", "review", "low")}
    if got != T["val"]["band_counts"]:
        raise GateError(f"band counts {got} != thresholds.json {T['val']['band_counts']}")
    fil = int(((band == "low") & y).sum())
    if fil != T["val"]["low"]["fraud_in_low"]:
        raise GateError(f"fraud in LOW {fil} != thresholds.json {T['val']['low']['fraud_in_low']}")

    overall = group_stats(band, y, np.ones(len(y), bool))
    ref = R["banding_v2"]["fairness"]["groups"]["customer_country"]
    groups = {}
    for g in COUNTRIES:
        st = group_stats(band, y, country == g)
        r = ref[g]
        # Gate 4: per-country reproduction
        mine = (st["n"], st["positives"], st["missed_fraud"]["k"])
        theirs = (r["n"], r["positives"], r["fraud_in_low"])
        if mine != theirs:
            raise GateError(f"{g}: (n, positives, fraud_in_low) {mine} != val_results {theirs}")
        st["escalation_ratio_vs_overall"] = st["review_share"] / overall["review_share"]
        st["legit_escalation_ratio_vs_overall"] = (
            st["legit_escalated_share"] / overall["legit_escalated_share"]
        )
        st["ml_engineer_escalate_fpr_ratio"] = r["escalate_fpr_ratio"]
        st["small_sample"] = st["positives"] < 30
        groups[g] = st
    other = sorted(set(country) - set(COUNTRIES))
    if other:
        raise GateError(f"unexpected customer_country values in VAL: {other}")

    # Routing order: add the Pending/Reversed VAL rows (HIGH first, else rule path).
    lo_ts, hi_ts = manifest["cutoff_train_end"], manifest["cutoff_val_end"]
    pr = con.execute(
        """
        SELECT customer_country, is_fraud, fraud_score
        FROM gold.transactions_masked
        WHERE transaction_status IN ('Pending', 'Reversed')
          AND transaction_ts_utc >= CAST(? AS TIMESTAMP)
          AND transaction_ts_utc <  CAST(? AS TIMESTAMP)
        """,
        [lo_ts, hi_ts],
    ).df()
    pr_fs = pd.to_numeric(pr["fraud_score"].astype("object"), errors="coerce").to_numpy("float64")
    pr_hi = np.nan_to_num(pr_fs, nan=-np.inf) > HIGH_VALUE
    pr_y = pr["is_fraud"].astype(bool).to_numpy()
    pr_c = pr["customer_country"].astype("object").fillna("__NA__").to_numpy()
    ref_pr = R["pending_reversed_high"]["val"]["Pending+Reversed"]
    mine_pr = (len(pr), int(pr_y.sum()), int(pr_hi.sum()))
    theirs_pr = (ref_pr["rows"], ref_pr["fraud"], ref_pr["high_rows"])
    # Gate 5
    if mine_pr != theirs_pr:
        raise GateError(f"Pending/Reversed VAL (rows, fraud, high) {mine_pr} != {theirs_pr}")

    def routing(mask_model, mask_pr) -> dict:
        m_low = int(((band == "low") & mask_model).sum())
        m_rev = int(((band == "review") & mask_model).sum())
        m_high = int(((band == "high") & mask_model).sum())
        p_high = int((pr_hi & mask_pr).sum())
        p_rule = int((~pr_hi & mask_pr).sum())
        n = m_low + m_rev + m_high + p_high + p_rule
        return {
            "n": n,
            "high_share": (m_high + p_high) / n,
            "rule_path_share": p_rule / n,
            "low_share": m_low / n,
            "review_share": m_rev / n,
            "fraud_on_rule_path": int((~pr_hi & mask_pr & pr_y).sum()),
        }

    r_all = routing(np.ones(len(y), bool), np.ones(len(pr), bool))
    overall["routing_order"] = r_all

    # Gate 6 (only with --routing-split): the ML Engineer's routing-order totals must match.
    routing_check = None
    if args.routing_split:
        rs_path = _require(Path(args.routing_split), "ML Engineer routing-order split JSON")
        rs = json.loads(rs_path.read_text())
        tot = rs.get("totals", rs)
        need = ("n_charges", "n_high", "n_rule", "n_low", "n_review")
        missing = [k for k in need if k not in tot]
        if missing:
            sys.exit(f"ROUTING SPLIT SCHEMA MISMATCH: missing keys {missing} in {rs_path}")
        n_all = r_all["n"]
        mine_rs = {
            "n_charges": n_all,
            "n_high": round(r_all["high_share"] * n_all),
            "n_rule": round(r_all["rule_path_share"] * n_all),
            "n_low": round(r_all["low_share"] * n_all),
            "n_review": round(r_all["review_share"] * n_all),
        }
        theirs_rs = {k: int(tot[k]) for k in need}
        if mine_rs != theirs_rs:
            raise GateError(f"routing-order totals {mine_rs} != ML Engineer split {theirs_rs}")
        routing_check = {"source": str(rs_path), "matched": True, **theirs_rs}
    for g in COUNTRIES:
        rg = routing(country == g, pr_c == g)
        rg["escalation_ratio_vs_overall"] = rg["review_share"] / r_all["review_share"]
        groups[g]["routing_order"] = rg

    out = {
        "label": "validation set",
        "split": "validation",
        "test_set_used": False,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "analytics/fairness.py",
        "thresholds_version": T["version"],
        "t_low": t_low,
        "t_low_source": "thresholds.json key t_low (raw LightGBM score, 95% recall target)",
        "high_rule": "fraud_score > 30 (fixed, checked first)",
        "definitions": {
            "model_scope": "Approved/Declined VAL charges (ML scope). Bands: HIGH, REVIEW, LOW.",
            "low_share": "LOW (AI auto-resolves) / n",
            "review_share": "REVIEW (human handoff) / n",
            "escalation_ratio_vs_overall": "group review_share / overall review_share",
            "legit_escalation_ratio_vs_overall": (
                "group share of legit charges sent to a human (REVIEW or HIGH) / overall share"
            ),
            "missed_fraud": "fraud in LOW / all fraud in group; Wilson 95% interval, z=1.96",
            "routing_order": (
                "all VAL charges incl. Pending/Reversed: HIGH first, then the deterministic "
                "Pending/Reversed rule path, then LOW/REVIEW. fraud_on_rule_path = fraud that the "
                "rule path explains without the model (not counted as missed fraud above)."
            ),
        },
        "reproduction_gates": {
            "model_sha256": model_sha,
            "val_sha256_sorted_keys": val_hash,
            "band_counts": got,
            "fraud_in_low": fil,
            "pending_reversed_val_rows_fraud_high": list(mine_pr),
            "per_country_matches_val_results": True,
            "routing_split_check": routing_check,
        },
        "overall": overall,
        "by_customer_country": groups,
        "language_es_vs_pt": {
            "status": "not computed here; comes from the eval set after the Oct 2 eval run",
            "label": "on the eval set, PT machine-translated",
            "sql": EVAL_LANGUAGE_SQL.strip(),
        },
    }
    p = out_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GateError as e:
        sys.exit(f"REPRODUCTION GATE FAILED, nothing written: {e}")
