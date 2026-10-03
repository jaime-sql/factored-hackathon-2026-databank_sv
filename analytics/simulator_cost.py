"""Add expected cost per case to the ML Engineer's simulator curve (validation set).

The ML Engineer owns static/data/sim_curve.json (200 cut points, routing order, validation set).
Curve schema (sim-curve-v1): top level n_charges, n_high, n_rule, t_low_default, fraud_in_high,
fraud_in_rule, points[]; per point cut, n_low, n_review, automation_rate, missed_fraud{k, n, rate,
ci_low, ci_high}, recall_outside_low, fraud_in_low_per_10k_low, cost_per_case (null until filled),
optional default (true on the t_low_default point).

This script FILLS cost fields and never changes the ML Engineer's other fields:
  - per point "cost_per_case"        {low, mid, high}: expected cost per charge (USD)
  - per point "human_only"           {low, mid, high}: human-only cost per charge (USD)
  - per point "net_savings_per_case" {low, mid, high}: human_only - cost_per_case (USD)
  - top level "cost_model"            inputs, sources, assumptions
  - top level "default_point_summary" the t_low_default point, for quoting one number
A null (or absent) cost field is fillable. A non-null one is overwritten only if the curve's
"cost_model" was written by this script; otherwise the script stops.

Shares of all validation charges, derived from counts (must add up exactly):
  low = n_low/n_charges, review = n_review/n_charges, high = n_high/n_charges,
  rule = n_rule/n_charges, with n_low + n_review + n_high + n_rule == n_charges.

Cost model, per charge, in routing order (HIGH first, then the Pending/Reversed rule path, then
LOW/REVIEW):
  LOW    (AI resolves)                       -> llm_low
  REVIEW (human handoff)                     -> llm_review + human_cost
  HIGH   (fraud_score > 30: block offer +
          human handoff)                     -> llm_high + human_cost      [ASSUMPTION A1]
  RULE   (Pending/Reversed template answer)  -> llm_rule (default 0), no human  [ASSUMPTION A2]
  expected = sum(llm_band * share_band) + human * (review + high)
  human-only baseline = human_cost for every charge                        [ASSUMPTION A3]
A1: the agent still runs its LLM turn on HIGH cases before the handoff.
A2: the rule path is template-only (dashboard_spec K9: case cost is 0 when there are no LLM calls).
    Override with --rule-path-llm-cost, or calls_per_case.rule in the cost JSON.
A3: in a human-only desk every dispute costs one human resolution, including Pending/Reversed.
Human cost per dispute resolution (team-locked): $1.66 / $3.32 / $5.53 (low / mid at $12/hr / high),
from analytics/out/cost_proj_per_resolution.csv on main (Queja, mean handle time).

LLM cost inputs (measured from QA audit rows), one of:
  --llm-cost-usd X       flat LLM cost per case for LOW/REVIEW/HIGH
  --llm-cost-json FILE   either {"llm_cost_per_case_usd": X, "source": ..., "eval_run_id": ...}
                         or {"cost_per_call_usd": c,
                             "calls_per_case": {"low": a, "review": b, "high": h, "rule": r},
                             "source": ..., "eval_run_id": ...}
                         (per band llm = c * calls; "rule" optional, absent -> A2 default)

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
BANDS = ("low", "review", "high", "rule")
COST_KEYS = ("cost_per_case", "human_only", "net_savings_per_case")
TOP_COUNT_KEYS = ("n_charges", "n_high", "n_rule")
AUTOMATION_TOL = 1e-5  # automation_rate is rounded to 6 decimals in the curve
NDIGITS = 6


class InputError(ValueError):
    pass


def _points(curve: dict) -> list[dict]:
    pts = curve.get("points")
    if not isinstance(pts, list):
        raise InputError("curve has no 'points' list")
    return pts


def _count(d: dict, key: str, where: str) -> int:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise InputError(f"{where}: '{key}' must be an integer >= 0, got {v!r}")
    return v


def point_shares(curve: dict, p: dict, i: int = 0) -> dict:
    """Shares of all validation charges for one cut, derived from counts. Fails if counts don't
    add up to n_charges or if automation_rate disagrees with (n_low + n_rule) / n_charges."""
    n = _count(curve, "n_charges", "curve")
    if n == 0:
        raise InputError("curve: n_charges is 0")
    counts = {
        "low": _count(p, "n_low", f"point {i}"),
        "review": _count(p, "n_review", f"point {i}"),
        "high": _count(curve, "n_high", "curve"),
        "rule": _count(curve, "n_rule", "curve"),
    }
    total = sum(counts.values())
    if total != n:
        raise InputError(
            f"point {i}: n_low + n_review + n_high + n_rule = {total} != n_charges = {n} "
            f"({counts}); shares would not sum to 1"
        )
    shares = {b: counts[b] / n for b in BANDS}
    if abs(sum(shares.values()) - 1.0) > 1e-9:
        raise InputError(f"point {i}: shares sum to {sum(shares.values())}, expected 1")
    ar = p.get("automation_rate")
    if ar is not None and abs(float(ar) - (shares["low"] + shares["rule"])) > AUTOMATION_TOL:
        raise InputError(
            f"point {i}: automation_rate {ar} != (n_low + n_rule) / n_charges "
            f"= {shares['low'] + shares['rule']:.6f}"
        )
    return shares


def check_curve(curve: dict) -> None:
    split = str(curve.get("split", curve.get("label", ""))).lower()
    if "validation" not in split:
        raise InputError(f"curve split/label must be the validation set, got {split!r}")
    if "test" in split.replace("test_fixture", ""):
        raise InputError("curve mentions the test set; the simulator uses the validation set only")
    for k in TOP_COUNT_KEYS:
        if k not in curve:
            raise InputError(f"curve is missing top-level '{k}'")
    pts = _points(curve)
    if not pts:
        raise InputError("curve has zero points")
    for i, p in enumerate(pts):
        point_shares(curve, p, i)


def cost_for_point(shares: dict, band_llm: dict) -> dict:
    """Return {"cost_per_case", "human_only", "net_savings_per_case"}, each {low, mid, high}."""
    llm_part = sum(band_llm[b] * shares[b] for b in BANDS)
    human_share = shares["review"] + shares["high"]
    expected, human_only, net = {}, {}, {}
    for scen, human in HUMAN_COST_USD.items():
        e = llm_part + human * human_share
        expected[scen] = round(e, NDIGITS)
        human_only[scen] = human
        net[scen] = round(human - e, NDIGITS)
    return {"cost_per_case": expected, "human_only": human_only, "net_savings_per_case": net}


def _finite_nonneg(v: object, what: str) -> float:
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError) as e:
        raise InputError(f"{what} must be a number, got {v!r}") from e
    if not (f >= 0) or math.isinf(f):
        raise InputError(f"{what} must be a finite number >= 0, got {v!r}")
    return f


def band_costs_from_json(d: dict, rule_llm: float, where: str) -> tuple[dict, dict]:
    """Per band LLM cost from a cost JSON (flat or calls-per-case form) plus metadata."""
    has_flat = "llm_cost_per_case_usd" in d
    has_calls = "cost_per_call_usd" in d or "calls_per_case" in d
    if has_flat and has_calls:
        raise InputError(f"{where}: give llm_cost_per_case_usd OR cost_per_call_usd+calls_per_case")
    meta = {k: d[k] for k in ("source", "eval_run_id", "measured_on") if k in d}
    meta.setdefault("source", where)
    if has_flat:
        v = _finite_nonneg(d["llm_cost_per_case_usd"], f"{where}: llm_cost_per_case_usd")
        meta["form"] = "flat llm_cost_per_case_usd"
        return {"low": v, "review": v, "high": v, "rule": rule_llm}, meta
    if not has_calls:
        raise InputError(
            f"{where} has neither 'llm_cost_per_case_usd' nor 'cost_per_call_usd'+'calls_per_case'"
        )
    if "cost_per_call_usd" not in d or not isinstance(d.get("calls_per_case"), dict):
        raise InputError(
            f"{where}: calls form needs 'cost_per_call_usd' and a 'calls_per_case' dict"
        )
    cpc = _finite_nonneg(d["cost_per_call_usd"], f"{where}: cost_per_call_usd")
    calls = d["calls_per_case"]
    unknown = set(calls) - set(BANDS)
    if unknown:
        raise InputError(f"{where}: calls_per_case has unknown bands {sorted(unknown)}")
    out = {}
    for b in ("low", "review", "high"):
        if b not in calls:
            raise InputError(f"{where}: calls_per_case is missing '{b}'")
        out[b] = cpc * _finite_nonneg(calls[b], f"{where}: calls_per_case.{b}")
    if "rule" in calls:
        if rule_llm != 0.0:
            raise InputError("give calls_per_case.rule or --rule-path-llm-cost, not both")
        out["rule"] = cpc * _finite_nonneg(calls["rule"], f"{where}: calls_per_case.rule")
    else:
        out["rule"] = rule_llm
    meta.update(
        form="cost_per_call_usd x calls_per_case",
        cost_per_call_usd=cpc,
        calls_per_case={b: calls[b] for b in BANDS if b in calls},
    )
    return out, meta


def load_llm_cost(args: argparse.Namespace) -> tuple[dict, dict]:
    rule_llm = _finite_nonneg(args.rule_path_llm_cost, "--rule-path-llm-cost")
    if args.llm_cost_usd is not None and args.llm_cost_json:
        raise InputError("give --llm-cost-usd or --llm-cost-json, not both")
    if args.llm_cost_usd is not None:
        v = _finite_nonneg(args.llm_cost_usd, "--llm-cost-usd")
        meta = {"source": "CLI --llm-cost-usd", "form": "flat llm_cost_per_case_usd"}
        return {"low": v, "review": v, "high": v, "rule": rule_llm}, meta
    if args.llm_cost_json:
        p = Path(args.llm_cost_json)
        if not p.exists():
            raise InputError(f"MISSING INPUT: LLM cost JSON not found at {p}")
        d = json.loads(p.read_text())
        if not isinstance(d, dict):
            raise InputError(f"{p} must contain a JSON object")
        return band_costs_from_json(d, rule_llm, str(p))
    raise InputError(
        "MISSING INPUT: LLM cost (measured from QA audit rows). "
        "Pass --llm-cost-usd or --llm-cost-json."
    )


def default_point_index(curve: dict) -> tuple[int, str]:
    pts = _points(curve)
    flagged = [i for i, p in enumerate(pts) if p.get("default") is True]
    if len(flagged) > 1:
        raise InputError(f"curve has {len(flagged)} points with default: true")
    if flagged:
        return flagged[0], "point flagged default: true"
    t = curve.get("t_low_default")
    if t is None:
        raise InputError("curve has no t_low_default and no point flagged default: true")
    t = float(t)
    exact = [i for i, p in enumerate(pts) if float(p.get("cut", math.nan)) == t]
    if exact:
        return exact[0], "cut == t_low_default"
    i = min(range(len(pts)), key=lambda j: abs(float(pts[j].get("cut", math.inf)) - t))
    return i, f"nearest cut to t_low_default (|diff| = {abs(float(pts[i]['cut']) - t):.3g})"


def enrich(curve: dict, band_llm: dict, llm_meta: dict, note: str | None = None) -> dict:
    """Return a copy of curve with cost fields filled. Other existing fields are left unchanged."""
    if set(band_llm) != set(BANDS):
        raise InputError(f"band_llm must have exactly the bands {BANDS}")
    check_curve(curve)
    prev = curve.get("cost_model")
    ours = isinstance(prev, dict) and prev.get("generator") == GENERATOR
    if prev is not None and not ours:
        raise InputError("curve already has a 'cost_model' key not written by this script")
    for k in ("default_point_summary",):
        if curve.get(k) is not None and not ours:
            raise InputError(f"curve already has '{k}' not written by this script")
    out = json.loads(json.dumps(curve))
    pts = _points(out)
    for i, p in enumerate(pts):
        for k in COST_KEYS:
            if p.get(k) is not None and not ours:
                raise InputError(
                    f"point {i} already has a non-null '{k}' not written by this script"
                )
    for i, p in enumerate(pts):
        p.update(cost_for_point(point_shares(out, p, i), band_llm))

    di, how = default_point_index(out)
    dp = pts[di]
    ds = point_shares(out, dp, di)
    out["cost_model"] = {
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **({"note": note} if note else {}),
        "llm_cost_per_case_usd_by_band": band_llm,
        "llm_cost_source": llm_meta,
        "llm_cost_label": "measured from 22 QA audit rows (live calls)",
        "human_cost_per_resolution_usd": HUMAN_COST_USD,
        "human_cost_source": HUMAN_COST_SOURCE,
        "shares": "low=n_low/n_charges, review=n_review/n_charges, high=n_high/n_charges, "
        "rule=n_rule/n_charges (validation set)",
        "formula": "expected = sum(llm_band*share_band) + human*(review+high); "
        "human_only = human per charge; net_savings_per_case = human_only - expected",
        "fields": "per point cost_per_case / human_only / net_savings_per_case, each "
        "{low, mid, high} human-cost scenario, USD per charge",
        "assumptions": [
            "A1: HIGH cases cost one LLM turn (llm_high) plus one human resolution.",
            (
                "A2: the Pending/Reversed rule path is template-only (llm_rule, default 0) and "
                "never needs a human."
            ),
            "A3: human-only baseline = one human resolution per charge.",
        ],
    }
    mid_saving = dp["net_savings_per_case"]["mid"]
    out["default_point_summary"] = {
        "point_index": di,
        "matched_by": how,
        "cut": dp.get("cut"),
        "t_low_default": out.get("t_low_default"),
        "automation_rate": dp.get("automation_rate"),
        "missed_fraud": dp.get("missed_fraud"),
        "shares": {b: round(ds[b], NDIGITS) for b in BANDS},
        "cost_per_case": dp["cost_per_case"],
        "human_only": dp["human_only"],
        "net_savings_per_case": dp["net_savings_per_case"],
        "net_savings_pct_vs_human_only": {
            s: round(dp["net_savings_per_case"][s] / HUMAN_COST_USD[s], NDIGITS)
            for s in HUMAN_COST_USD
        },
        "quote_mid": (
            f"At the default cut ({dp.get('automation_rate', 0) * 100:.2f}% automation), "
            f"expected ${dp['cost_per_case']['mid']:.2f} per charge vs "
            f"${HUMAN_COST_USD['mid']:.2f} human-only: ${mid_saving:.2f} saved per charge "
            "(mid scenario, validation set)."
        ),
    }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--curve", default=str(SHIPPED_CURVE), help="ML Engineer curve JSON")
    ap.add_argument("--llm-cost-usd", type=float, default=None)
    ap.add_argument("--llm-cost-json", default=None)
    ap.add_argument("--rule-path-llm-cost", type=float, default=0.0)
    ap.add_argument("--note", default=None, help="free-text note stored in cost_model")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--in-place", action="store_true", help="fill fields in --curve itself")
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
        band_llm, meta = load_llm_cost(args)
        out_path = cp if args.in_place else Path(args.out)
        if curve.get("test_fixture") and out_path.resolve().parent == SHIPPED_CURVE.parent:
            raise InputError("refusing to write a test_fixture curve into static/data")
        enriched = enrich(curve, band_llm, meta, args.note)
    except (InputError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(enriched, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out_path}")
    print(enriched["default_point_summary"]["quote_mid"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
