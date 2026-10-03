"""Tests for analytics/simulator_cost.py and the Wilson helper in analytics/fairness.py.

Uses only tests/fixtures/test_fixture_sim_curve.json (synthetic, shaped like the ML Engineer's
sim-curve-v1: counts per point, cost_per_case null; never shipped as data).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "test_fixture_sim_curve.json"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "analytics" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sim = _load("simulator_cost")
fair = _load("fairness")


def _curve() -> dict:
    return json.loads(FIXTURE.read_text())


def _flat(v: float, rule: float = 0.0) -> dict:
    return {"low": v, "review": v, "high": v, "rule": rule}


def test_share_derivation_from_counts() -> None:
    curve = _curve()
    s = sim.point_shares(curve, curve["points"][1], 1)
    assert s == pytest.approx({"low": 0.4, "review": 0.4, "high": 0.1, "rule": 0.1})
    assert sum(s.values()) == pytest.approx(1.0)


def test_counts_not_adding_up_fail_loudly() -> None:
    curve = _curve()
    curve["points"][0]["n_review"] = 79
    with pytest.raises(sim.InputError, match="n_charges"):
        sim.enrich(curve, _flat(0.01), {})
    curve = _curve()
    curve["n_rule"] = 11
    with pytest.raises(sim.InputError, match="n_charges"):
        sim.check_curve(curve)
    curve = _curve()
    del curve["n_high"]
    with pytest.raises(sim.InputError):
        sim.check_curve(curve)


def test_automation_rate_mismatch_fails() -> None:
    curve = _curve()
    curve["points"][1]["automation_rate"] = 0.6
    with pytest.raises(sim.InputError, match="automation_rate"):
        sim.check_curve(curve)


def test_cost_math_and_null_fill() -> None:
    curve = _curve()
    assert all(p["cost_per_case"] is None for p in curve["points"])
    assert "cost_model" not in curve
    out = sim.enrich(curve, _flat(0.01), {"source": "test"})
    p = out["points"][1]  # low .4, review .4, high .1, rule .1 -> llm*.9 + human*.5
    exp_mid = 0.01 * 0.9 + 3.32 * 0.5
    assert p["cost_per_case"]["mid"] == pytest.approx(exp_mid, abs=1e-6)
    assert p["human_only"] == {"low": 1.66, "mid": 3.32, "high": 5.53}
    assert p["net_savings_per_case"]["mid"] == pytest.approx(3.32 - exp_mid, abs=1e-6)
    assert out["cost_model"]["generator"] == sim.GENERATOR
    costs = [q["cost_per_case"]["low"] for q in out["points"]]
    assert costs == sorted(costs, reverse=True)  # more automation -> cheaper


def test_existing_fields_unchanged() -> None:
    curve = _curve()
    out = sim.enrich(curve, _flat(0.02), {})
    for k, v in curve.items():
        if k != "points":
            assert out[k] == v
    for a, b in zip(curve["points"], out["points"], strict=True):
        assert {k: b[k] for k in a if k != "cost_per_case"} == {
            k: v for k, v in a.items() if k != "cost_per_case"
        }


def test_refuses_to_overwrite_foreign_non_null_cost() -> None:
    curve = _curve()
    curve["points"][2]["cost_per_case"] = {"mid": 1.0}
    with pytest.raises(sim.InputError, match="non-null 'cost_per_case'"):
        sim.enrich(curve, _flat(0.01), {})
    curve = _curve()
    curve["points"][0]["net_savings_per_case"] = {"mid": 1.0}
    with pytest.raises(sim.InputError):
        sim.enrich(curve, _flat(0.01), {})


def test_refuses_foreign_cost_model_but_reruns_own() -> None:
    curve = _curve()
    curve["cost_model"] = {"generator": "someone-else"}
    with pytest.raises(sim.InputError):
        sim.enrich(curve, _flat(0.01), {})
    once = sim.enrich(_curve(), _flat(0.01), {})
    twice = sim.enrich(once, _flat(0.02), {})  # own output can be refreshed
    assert twice["points"][1]["cost_per_case"]["mid"] == pytest.approx(
        0.02 * 0.9 + 3.32 * 0.5, abs=1e-6
    )


def test_null_cost_model_is_fillable() -> None:
    curve = _curve()
    curve["cost_model"] = None
    out = sim.enrich(curve, _flat(0.01), {})
    assert out["cost_model"]["generator"] == sim.GENERATOR


def test_per_band_calls(tmp_path: Path) -> None:
    d = {
        "cost_per_call_usd": 0.002,
        "calls_per_case": {"low": 2, "review": 3, "high": 1},
        "source": "test",
        "eval_run_id": "r1",
    }
    band, meta = sim.band_costs_from_json(d, 0.0, "x")
    assert band == pytest.approx({"low": 0.004, "review": 0.006, "high": 0.002, "rule": 0.0})
    assert meta["eval_run_id"] == "r1" and meta["calls_per_case"]["review"] == 3
    out = sim.enrich(_curve(), band, meta)
    llm = 0.004 * 0.4 + 0.006 * 0.4 + 0.002 * 0.1
    assert out["points"][1]["cost_per_case"]["high"] == pytest.approx(llm + 5.53 * 0.5, abs=1e-6)
    d["calls_per_case"]["rule"] = 1
    band, _ = sim.band_costs_from_json(d, 0.0, "x")
    assert band["rule"] == pytest.approx(0.002)
    with pytest.raises(sim.InputError, match="not both"):
        sim.band_costs_from_json(d, 0.001, "x")
    with pytest.raises(sim.InputError, match="missing 'high'"):
        sim.band_costs_from_json(
            {"cost_per_call_usd": 0.1, "calls_per_case": {"low": 1, "review": 1}}, 0.0, "x"
        )
    with pytest.raises(sim.InputError):
        sim.band_costs_from_json({"llm_cost_per_case_usd": 0.1, "cost_per_call_usd": 0.1}, 0.0, "x")
    # end to end through the CLI, flat JSON form still works
    cj = tmp_path / "flat.json"
    cj.write_text(json.dumps({"llm_cost_per_case_usd": 0.01, "source": "t"}))
    o = tmp_path / "o.json"
    assert sim.main(["--curve", str(FIXTURE), "--llm-cost-json", str(cj), "--out", str(o)]) == 0
    assert json.loads(o.read_text())["cost_model"]["llm_cost_source"]["source"] == "t"


def test_default_point_summary() -> None:
    out = sim.enrich(_curve(), _flat(0.01), {})
    s = out["default_point_summary"]
    assert s["point_index"] == 1 and s["matched_by"] == "point flagged default: true"
    assert s["automation_rate"] == 0.5 and s["missed_fraud"]["k"] == 1
    curve = _curve()
    del curve["points"][1]["default"]
    curve["t_low_default"] = 0.29
    s = sim.enrich(curve, _flat(0.01), {})["default_point_summary"]
    assert s["point_index"] == 2 and s["matched_by"].startswith("nearest")


def test_missing_inputs_fail(tmp_path: Path) -> None:
    o = tmp_path / "o.json"
    args = ["--curve", str(tmp_path / "nope.json"), "--llm-cost-usd", "0.01", "--out", str(o)]
    assert sim.main(args) == 2
    assert sim.main(["--curve", str(FIXTURE), "--out", str(o)]) == 2
    assert not o.exists()


def test_rejects_non_validation() -> None:
    curve = _curve()
    curve["split"] = "test"
    with pytest.raises(sim.InputError):
        sim.enrich(curve, _flat(0.01), {})


def test_default_path_is_repo_static_data() -> None:
    assert sim.SHIPPED_CURVE == ROOT / "static" / "data" / "sim_curve.json"


def test_wilson_matches_dashboard_reference() -> None:
    w = fair.wilson(29, 599)
    assert w["ci95_low"] == pytest.approx(0.033917781042, abs=1e-11)
    assert w["ci95_high"] == pytest.approx(0.068665506679, abs=1e-11)
    assert fair.wilson(0, 0)["rate"] is None
