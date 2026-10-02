"""Tests for analytics/simulator_cost.py and the Wilson helper in analytics/fairness.py.

Uses only tests/fixtures/test_fixture_sim_curve.json (synthetic, never shipped as data).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "test_fixture_sim_curve.json"
T_LOW_DEFAULT = 0.000275603870032301


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "analytics" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sim = _load("simulator_cost")
fair = _load("fairness")


def test_fixture_matches_confirmed_schema() -> None:
    curve = json.loads(FIXTURE.read_text())
    assert curve["split"] == "validation"
    assert curve["t_low_default"] == pytest.approx(T_LOW_DEFAULT)
    defaults = [p for p in curve["points"] if p["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["t_low"] == pytest.approx(T_LOW_DEFAULT)
    t_lows = [p["t_low"] for p in curve["points"]]
    assert t_lows == sorted(t_lows)
    for p in curve["points"]:
        assert (
            curve["n_high"] + curve["n_rule"] + p["n_low"] + p["n_review"] == curve["n_charges"]
        )
        assert p["automation_rate"] == pytest.approx(
            (curve["n_rule"] + p["n_low"]) / curve["n_charges"]
        )
        assert p["missed_fraud_rate"] == pytest.approx(p["missed_fraud_n"] / curve["n_fraud"])
        assert p["wrongful_autoclose_per_10k"] == pytest.approx(
            p["missed_fraud_n"] / curve["n_charges"] * 10000
        )
        w = fair.wilson(p["missed_fraud_n"], curve["n_fraud"])
        assert p["missed_fraud_ci_lo"] == pytest.approx(w["ci95_low"])
        assert p["missed_fraud_ci_hi"] == pytest.approx(w["ci95_high"])


def test_cost_math_on_fixture() -> None:
    curve = json.loads(FIXTURE.read_text())
    out = sim.enrich(curve, llm=0.01, llm_meta={"source": "test"}, rule_llm=0.0)
    # default point: n_low 40, n_review 40, n_high 10, n_rule 10, n_charges 100
    # -> llm*(40+40+10)/100 + human*(40+10)/100
    mid = out["points"][1]["cost_per_case"]["mid"]
    assert mid["expected_cost_per_case_usd"] == pytest.approx(0.01 * 0.9 + 3.32 * 0.5)
    assert mid["human_only_cost_per_case_usd"] == 3.32
    assert out["points"][1]["missed_fraud_n"] == curve["points"][1]["missed_fraud_n"]
    assert out["points"][1]["automation_rate"] == curve["points"][1]["automation_rate"]
    assert out["cost_model"]["generator"] == sim.GENERATOR
    # more automation -> cheaper
    costs = [p["cost_per_case"]["low"]["expected_cost_per_case_usd"] for p in out["points"]]
    assert costs == sorted(costs, reverse=True)


def test_existing_fields_unchanged() -> None:
    curve = json.loads(FIXTURE.read_text())
    out = sim.enrich(curve, 0.02, {}, 0.0)
    for k, v in curve.items():
        if k != "points":
            assert out[k] == v
    for a, b in zip(curve["points"], out["points"], strict=True):
        assert {k: b[k] for k in a} == a


def test_missing_inputs_fail(tmp_path: Path) -> None:
    assert (
        sim.main(
            [
                "--curve",
                str(tmp_path / "nope.json"),
                "--llm-cost-usd",
                "0.01",
                "--out",
                str(tmp_path / "o.json"),
            ]
        )
        == 2
    )
    assert sim.main(["--curve", str(FIXTURE), "--out", str(tmp_path / "o.json")]) == 2
    assert not (tmp_path / "o.json").exists()


def test_rejects_non_validation_and_bad_routing_totals() -> None:
    curve = json.loads(FIXTURE.read_text())
    curve["split"] = "test"
    with pytest.raises(sim.InputError):
        sim.enrich(curve, 0.01, {}, 0.0)
    curve = json.loads(FIXTURE.read_text())
    curve["points"][0]["n_review"] = 50
    with pytest.raises(sim.InputError, match="routing totals"):
        sim.enrich(curve, 0.01, {}, 0.0)


def test_refuses_foreign_cost_model() -> None:
    curve = json.loads(FIXTURE.read_text())
    curve["cost_model"] = {"generator": "someone-else"}
    with pytest.raises(sim.InputError):
        sim.enrich(curve, 0.01, {}, 0.0)


def test_wilson_matches_dashboard_reference() -> None:
    w = fair.wilson(29, 610)
    assert w["ci95_low"] == pytest.approx(0.033302414391, abs=1e-11)
    assert w["ci95_high"] == pytest.approx(0.067442587323, abs=1e-11)
    assert fair.wilson(0, 0)["rate"] is None


def test_no_shares_output_has_no_share_or_band_counts() -> None:
    st = {
        "n": 100,
        "positives": 10,
        "positives_pending_reversed": 1,
        "positives_all_statuses": 11,
        "low_n": 20,
        "review_n": 79,
        "high_n": 1,
        "low_share": 0.2,
        "review_share": 0.79,
        "high_share": 0.01,
        "missed_fraud": fair.wilson(2, 11),
        "escalation_ratio_vs_overall": 1.0,
        "small_sample": True,
    }
    out = fair.embargo_safe({"version": "v"}, 0.1, "m", "h", 2, dict(st), {"Mexico": dict(st)})
    text = json.dumps(out)
    for banned in (
        "low_share",
        "review_share",
        "high_share",
        "low_n",
        "review_n",
        "high_n",
        'band_counts"',
        "routing_order",
        "seguro",
    ):
        assert banned not in text, banned
    assert out["by_customer_country"]["Mexico"]["missed_fraud"]["n"] == 11
