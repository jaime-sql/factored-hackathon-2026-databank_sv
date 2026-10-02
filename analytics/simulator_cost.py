"""Add expected cost per case to the ML Engineer's simulator curve (validation set).

The ML Engineer owns static/data/sim_curve.json (about 200 cut points, routing order, validation
set). This script ADDS cost fields to it and never changes their fields:
  - top-level key "cost_model" (inputs, assumptions, sources)
  - per point key "cost_per_case" (low / mid / high human-cost scenario vs human-only)
If either key already exists and was not written by this script, it stops.

Confirmed sim_curve.json fields (do not rename them):
  top level: split ("validation"), model_version, t_low_default, n_charges, n_fraud,
             n_high, n_rule, fraud_in_high, fraud_in_rule, points
  each point: t_low, is_default, n_low, n_review, automation_rate, missed_fraud_n,
              missed_fraud_rate, missed_fraud_ci_lo, missed_fraud_ci_hi,
              wrongful_autoclose_per_10k
n_high and n_rule are constants (the slider does not move them). At every point
n_high + n_rule + n_low + n_review == n_charges; the script exits non-zero if that fails.
automation_rate = (n_rule + n_low) / n_charges
missed_fraud_rate = missed_fraud_n / n_fraud   (fraud in LOW / n_fraud; Wilson 95% CI)
wrongful_autoclose_per_10k = missed_fraud_n / n_charges * 10000

Cost model, per charge, in routing order (HIGH first, then the Pending/Reversed rule path, then
LOW/REVIEW). Shares are counts over n_charges:
  LOW    (AI resolves)                       -> llm_cost
  REVIEW (human handoff)                     -> llm_cost + human_cost
  HIGH   (fraud_score > 30: block offer +
          human handoff)                     -> llm_cost + human_cost      [ASSUMPTION A1]
  RULE   (Pending/Reversed template answer)  -> rule_path_llm_cost (default 0), no human
                                                                           [ASSUMPTION A2]
  expected = llm*(n_low+n_review+n_high)/n_charges + rule_llm*n_rule/n_charges
             + human*(n_review+n_high)/n_charges
  human-only baseline = human_cost for every charge                        [ASSUMPTION A3]
A1: the agent still runs its LLM turn on HIGH cases before the handoff.
A2: the rule path is template-only (dashboard_spec K9: case cost is 0 when there are no LLM calls).
    Override with --rule-path-llm-cost once the eval run shows otherwise.
A3: in a human-only desk every dispute costs one human resolution, including Pending/Reversed.
Human cost per dispute resolution (team-locked): $1.66 / $3.32 / $5.53 (low / mid at $12/hr / high),
from analytics/out/cost_proj_per_resolution.csv on main (Queja, mean handle time).

LLM cost per case: measured in the Oct 2 eval run (on the eval set). Pass --llm-cost-usd X or
--llm-cost-json FILE with {"llm_cost_per_case_usd": X, "source": "...", "eval_run_id": "..."}.
There is no default.

Run:
  python analytics/simulator_cost.py --llm-cost-json eval_cost.json --in-place
  python analytics/simulator_cost.py --curve CURVE.json --llm-cost-usd X --out OUT.json
Fails loudly (non-zero exit, nothing written) when an input is missing or malformed. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHIPPED_CURVE = REPO / "static" / "data" / "sim_curve.json"
GENERATOR = "analytics/simulator_cost.py"
HUMAN_COST_USD = {"low": 1.66, "mid": 3.32, "high": 5.53}
HUMAN_COST_SOURCE = (
    "team-locked human cost per dispute resolution; analytics/out/cost_proj_per_resolution.csv "
    "(Queja, mean handle time 434.6 s, resolution rate 0.4364, $6/$12/$20 per hour)"
)
TOP_COUNT_KEYS = ("n_charges", "n_fraud", "n_high", "n_rule", "fraud_in_high", "fraud_in_rule")
TOL = 1e-6


class InputError(ValueError):
    pass


def _count(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{where} must be an integer count, got {value!r}")
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise InputError(f"{where} must be an integer count, got {value!r}")
        value = int(value)
    if value < 0:
        raise InputError(f"{where} must be >= 0, got {value}")
    return value


def _finite(value: object, where: str) -> float:
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as e:
        raise InputError(f"{where} must be a finite number, got {value!r}") from e
    if isinstance(value, bool) or not math.isfinite(v):
        raise InputError(f"{where} must be a finite number, got {value!r}")
    return v


def _close(got: float, expected: float, where: str) -> None:
    if not math.isclose(got, expected, rel_tol=0.0, abs_tol=TOL):
        raise InputError(f"{where}: got {got}, expected {expected}")


def check_curve(curve: dict) -> None:
    split = curve.get("split")
    if split != "validation":
        raise InputError(f"curve split must be 'validation', got {split!r}")
    if not isinstance(curve.get("model_version"), str) or not curve["model_version"]:
        raise InputError("curve model_version must be a non-empty string")
    _finite(curve.get("t_low_default"), "t_low_default")
    counts = {k: _count(curve.get(k), k) for k in TOP_COUNT_KEYS}
    n_charges = counts["n_charges"]
    n_fraud = counts["n_fraud"]
    n_high = counts["n_high"]
    n_rule = counts["n_rule"]
    if n_charges <= 0:
        raise InputError("n_charges must be > 0")
    if n_fraud <= 0:
        raise InputError("n_fraud must be > 0")
    pts = curve.get("points")
    if not isinstance(pts, list) or not pts:
        raise InputError("curve has no non-empty 'points' list")
    t_prev: float | None = None
    defaults = 0
    for i, p in enumerate(pts):
        if not isinstance(p, dict):
            raise InputError(f"point {i} is not an object")
        t_low = _finite(p.get("t_low"), f"point {i} t_low")
        if t_prev is not None and t_low < t_prev:
            raise InputError(f"point {i}: points must be sorted by t_low ascending")
        t_prev = t_low
        if not isinstance(p.get("is_default"), bool):
            raise InputError(f"point {i}: is_default must be a boolean")
        if p["is_default"]:
            defaults += 1
            _close(
                t_low,
                _finite(curve["t_low_default"], "t_low_default"),
                f"point {i} t_low vs t_low_default",
            )
        n_low = _count(p.get("n_low"), f"point {i} n_low")
        n_review = _count(p.get("n_review"), f"point {i} n_review")
        missed = _count(p.get("missed_fraud_n"), f"point {i} missed_fraud_n")
        total = n_high + n_rule + n_low + n_review
        if total != n_charges:
            raise InputError(
                f"point {i}: routing totals n_high + n_rule + n_low + n_review = {total} "
                f"!= n_charges {n_charges}"
            )
        _close(
            _finite(p.get("automation_rate"), f"point {i} automation_rate"),
            (n_rule + n_low) / n_charges,
            f"point {i} automation_rate",
        )
        _close(
            _finite(p.get("missed_fraud_rate"), f"point {i} missed_fraud_rate"),
            missed / n_fraud,
            f"point {i} missed_fraud_rate",
        )
        _close(
            _finite(p.get("wrongful_autoclose_per_10k"), f"point {i} wrongful_autoclose_per_10k"),
            missed / n_charges * 10000,
            f"point {i} wrongful_autoclose_per_10k",
        )
        lo = _finite(p.get("missed_fraud_ci_lo"), f"point {i} missed_fraud_ci_lo")
        hi = _finite(p.get("missed_fraud_ci_hi"), f"point {i} missed_fraud_ci_hi")
        if not (0.0 <= lo <= hi <= 1.0):
            raise InputError(f"point {i}: Wilson interval [{lo}, {hi}] is not inside [0, 1]")
    if defaults != 1:
        raise InputError(f"curve must have exactly one is_default point, found {defaults}")


def cost_for_point(
    n_charges: int, n_low: int, n_review: int, n_high: int, n_rule: int, llm: float, rule_llm: float
) -> dict:
    llm_part = llm * (n_low + n_review + n_high) / n_charges + rule_llm * n_rule / n_charges
    human_share = (n_review + n_high) / n_charges
    res = {}
    for scen, human in HUMAN_COST_USD.items():
        expected = llm_part + human * human_share
        res[scen] = {
            "human_cost_per_resolution_usd": human,
            "expected_cost_per_case_usd": expected,
            "human_only_cost_per_case_usd": human,
            "saving_per_case_usd": human - expected,
            "saving_pct_vs_human_only": (human - expected) / human,
        }
    return res


def load_llm_cost(args: argparse.Namespace) -> tuple[float, dict]:
    if args.llm_cost_usd is not None and args.llm_cost_json:
        raise InputError("give --llm-cost-usd or --llm-cost-json, not both")
    if args.llm_cost_usd is not None:
        v, meta = float(args.llm_cost_usd), {"source": "CLI --llm-cost-usd"}
    elif args.llm_cost_json:
        p = Path(args.llm_cost_json)
        if not p.exists():
            raise InputError(f"MISSING INPUT: LLM cost JSON not found at {p}")
        d = json.loads(p.read_text())
        if "llm_cost_per_case_usd" not in d:
            raise InputError(f"{p} has no 'llm_cost_per_case_usd'")
        v = float(d["llm_cost_per_case_usd"])
        meta = {k: d[k] for k in ("source", "eval_run_id", "measured_on") if k in d}
        meta.setdefault("source", str(p))
    else:
        raise InputError(
            "MISSING INPUT: LLM cost per case (measured in the Oct 2 eval run). "
            "Pass --llm-cost-usd or --llm-cost-json."
        )
    if not (v >= 0) or math.isinf(v):
        raise InputError(f"LLM cost per case must be a finite number >= 0, got {v}")
    return v, meta


def enrich(curve: dict, llm: float, llm_meta: dict, rule_llm: float) -> dict:
    """Return a copy of curve with cost fields added. Existing fields are left unchanged."""
    check_curve(curve)
    prev = curve.get("cost_model")
    if prev is not None and (not isinstance(prev, dict) or prev.get("generator") != GENERATOR):
        raise InputError("curve already has a 'cost_model' key not written by this script")
    out = json.loads(json.dumps(curve))
    n_charges = int(out["n_charges"])
    n_high = int(out["n_high"])
    n_rule = int(out["n_rule"])
    for i, p in enumerate(out["points"]):
        if "cost_per_case" in p and prev is None:
            raise InputError(f"point {i} already has 'cost_per_case' not written by this script")
        p["cost_per_case"] = cost_for_point(
            n_charges, int(p["n_low"]), int(p["n_review"]), n_high, n_rule, llm, rule_llm
        )
    out["cost_model"] = {
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "llm_cost_per_case_usd": llm,
        "llm_cost_source": llm_meta,
        "llm_cost_label": "measured on the eval set (Oct 2 eval run)",
        "rule_path_llm_cost_usd": rule_llm,
        "human_cost_per_resolution_usd": HUMAN_COST_USD,
        "human_cost_source": HUMAN_COST_SOURCE,
        "formula": (
            "llm*(n_low+n_review+n_high)/n_charges + rule_llm*n_rule/n_charges "
            "+ human*(n_review+n_high)/n_charges; human-only = human per charge"
        ),
        "assumptions": [
            "A1: HIGH cases cost one LLM turn plus one human resolution.",
            "A2: the Pending/Reversed rule path is template-only (rule_path_llm_cost_usd) and "
            "never needs a human.",
            "A3: human-only baseline = one human resolution per charge.",
        ],
    }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--curve", default=str(SHIPPED_CURVE), help="ML Engineer curve JSON")
    ap.add_argument("--llm-cost-usd", type=float, default=None)
    ap.add_argument("--llm-cost-json", default=None)
    ap.add_argument("--rule-path-llm-cost", type=float, default=0.0)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--in-place", action="store_true", help="add fields to --curve itself")
    g.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    try:
        cp = Path(args.curve)
        if not cp.exists():
            raise InputError(
                f"MISSING INPUT: curve JSON not found at {cp} "
                "(the ML Engineer pushes static/data/sim_curve.json)"
            )
        curve = json.loads(cp.read_text())
        llm, meta = load_llm_cost(args)
        out_path = cp if args.in_place else Path(args.out)
        if curve.get("test_fixture") and out_path.resolve().parent == SHIPPED_CURVE.parent:
            raise InputError("refusing to write a test_fixture curve into static/data")
        enriched = enrich(curve, llm, meta, float(args.rule_path_llm_cost))
    except (InputError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(enriched, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
