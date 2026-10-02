"""System health is live. Simulator, fairness, and trust appear only with their files."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.panels import fairness_panel, simulator_panel, trust_panel

_CURVE = {
    "split": "time",
    "model_version": "lgbm_v1",
    "t_low_default": 0.2,
    "n_charges": 100,
    "n_fraud": 4,
    "n_high": 3,
    "n_rule": 3,
    "fraud_in_high": 2,
    "fraud_in_rule": 2,
    "points": [
        {
            "t_low": 0.1,
            "is_default": False,
            "n_low": 40,
            "n_review": 57,
            "automation_rate": 0.4,
            "missed_fraud_n": 1,
            "missed_fraud_rate": 0.25,
            "missed_fraud_ci_lo": 0.01,
            "missed_fraud_ci_hi": 0.5,
            "wrongful_autoclose_per_10k": 2,
        },
        {
            "t_low": 0.2,
            "is_default": True,
            "n_low": 70,
            "n_review": 27,
            "automation_rate": 0.7,
            "missed_fraud_n": 2,
            "missed_fraud_rate": 0.5,
            "missed_fraud_ci_lo": 0.1,
            "missed_fraud_ci_hi": 0.8,
            "wrongful_autoclose_per_10k": 4,
        },
    ],
}


def test_metrics_health_and_hidden_panels(client: TestClient) -> None:
    body = client.get("/api/metrics?language=es").json()
    assert body["health"]["llm_calls"] == 0
    assert body["health"]["latency_p50_ms"] is None
    assert body["health"]["mean_cost_per_call_usd"] is None
    assert body["trust"] is None
    assert body["simulator"] is None
    fairness = body["fairness"]
    assert fairness["shares_included"] is False
    assert "Mexico" in fairness["by_customer_country"]
    assert "cause" not in fairness["by_customer_country"]["Mexico"]


def test_panels_render_only_when_files_exist(tmp_path: Path) -> None:
    assert trust_panel(tmp_path) is None
    assert simulator_panel(tmp_path) is None
    assert fairness_panel(tmp_path) is None
    data = tmp_path / "static" / "data"
    data.mkdir(parents=True)
    (data / "trust.json").write_text(
        json.dumps(
            [
                {
                    "label_es": "Corte al día",
                    "label_pt": "Corte em dia",
                    "value": "2026-10-01",
                    "ok": True,
                    "checked_at": "2026-10-01T00:00:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )
    (data / "sim_curve.json").write_text(json.dumps(_CURVE), encoding="utf-8")
    (data / "fairness.json").write_text(json.dumps({"groups": []}), encoding="utf-8")
    trust = trust_panel(tmp_path)
    assert trust is not None
    assert trust[0]["label_es"] == "Corte al día"
    sim = simulator_panel(tmp_path)
    assert sim is not None
    assert sim["show_cost"] is False
    assert sim["points"][1]["is_default"] is True
    assert fairness_panel(tmp_path) == {"groups": []}
    priced = json.loads(json.dumps(_CURVE))
    priced["points"][0]["cost_per_case"] = 0.42
    (data / "sim_curve.json").write_text(json.dumps(priced), encoding="utf-8")
    assert simulator_panel(tmp_path)["show_cost"] is True
