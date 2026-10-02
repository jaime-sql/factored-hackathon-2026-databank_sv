from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.bank.access import TRANSACTION_COLUMNS
from app.bank.repository import synthetic_pair_sibling
from app.thresholds_loader import ThresholdSource, preliminary_route
from app.timeutil import present_time
from app.triage_model import ScriptedTriage, fallback_score
from tests.conftest import login

ROOT = Path(__file__).resolve().parents[1]


def test_sqlite_personas_keep_synthetic_notes(client: TestClient) -> None:
    body = client.get("/api/personas").json()
    by_id = {row["id"]: row for row in body["personas"]}
    assert by_id["maria"]["segment"] == "Basic"
    assert by_id["maria"]["note"] == "Persona sintética"
    assert by_id["maria"]["notes"]["pt"] == "Pessoa sintética"
    assert by_id["teo"]["note"].startswith("Persona sintética")
    assert "Mexico City" not in by_id["teo"]["note"]
    assert by_id["lucia"]["label"] == "Lucía · Querétaro"
    assert by_id["lucia"]["labels"]["pt"] == "Lucía · Querétaro"
    assert by_id["lucia"]["segment"] == "Basic"
    assert by_id["lucia"]["tz"] == "America/Mexico_City"
    assert by_id["lucia"]["note"] == "Persona sintética, cargo duplicado"
    assert by_id["maria"]["labels"]["pt"] == "María · Cidade do México"
    assert by_id["camilo"]["label"] == "Camilo · Barranquilla"
    assert by_id["camilo"]["labels"]["pt"] == "Camilo · Barranquilla"
    assert by_id["ana"]["label"] == "Ana · Argentina"
    assert by_id["ana"]["labels"]["pt"] == "Ana · Argentina"
    assert synthetic_pair_sibling("SYN_0238_A") == "SYN_0238_B"
    assert synthetic_pair_sibling("SYN_0238_B") == "SYN_0238_A"
    assert synthetic_pair_sibling("tx_maria_dup_b") is None


def test_high_rule_runs_before_pending_and_reversed(client: TestClient) -> None:
    config = ThresholdSource(ROOT / "triage" / "artifacts" / "thresholds.json").get()
    assert config.high_op == ">"
    assert config.high_value == 30
    assert preliminary_route(31, "Pending", config) == "high"
    assert preliminary_route(30, "Pending", config) == "pending"
    assert preliminary_route(45, "Reversed", config) == "high"
    assert preliminary_route(None, "Pending", config) == "pending"

    headers = login(client, "maria")
    pending_high = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_pending_high", "message": "No reconozco este cargo"},
    ).json()
    assert pending_high["actions"][0]["id"] == "confirm_block"
    assert "Todavía no es definitivo" not in pending_high["reply"]
    assert pending_high["model_risk_score"] is None
    assert "nan" not in pending_high["reply"].lower()

    exact = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_pending_30", "message": "Ese cobro no lo hice yo"},
    ).json()
    assert exact["case_type"] == "pending"
    assert exact["actions"][0]["id"] == "contest"
    assert "pendiente" in exact["reply"].lower()
    assert "pendente" not in exact["reply"].lower()

    reversed_high = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_reversed_high", "message": "No reconozco este cargo"},
    ).json()
    assert reversed_high["actions"][0]["id"] == "confirm_block"
    assert "reversado" not in reversed_high["reply"].lower()


def test_pending_contest_hands_off_and_permissions_hold(client: TestClient) -> None:
    headers = login(client, "maria")
    opened = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_pending", "message": "No reconozco este cargo"},
    ).json()
    assert opened["actions"][0]["emphasis"] == "primary"
    assert opened["actions"][0]["label"] == "Sigo sin reconocer este cargo"
    blocked = client.post(
        f"/cases/{opened['case_id']}/actions",
        headers=headers,
        json={"action": "confirm_block"},
    )
    assert blocked.status_code == 403
    high = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_pending_high", "message": "No reconozco este cargo"},
    ).json()
    denied = client.post(
        f"/cases/{high['case_id']}/actions",
        headers=headers,
        json={"action": "contest"},
    )
    assert denied.status_code == 403
    confirmed = client.post(
        f"/cases/{high['case_id']}/actions",
        headers=headers,
        json={"action": "confirm_block"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert "Bloqueé" in confirmed.json()["reply"]
    events = client.app.state.ops.list_events(high["case_id"])
    assert any(
        event["name"] == "block_card" and event["verification_status"] == "verified"
        for event in events
    )
    packet = client.app.state.ops.get_handoff(high["case_id"])["packet"]
    assert packet["transaction"]["transaction_ts_utc"]
    assert packet["transaction"]["transaction_ts_customer_local"]
    assert "is_fraud" not in packet["transaction"]

    client.app.state.ops.readback_tamper = lambda _row: None
    again = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_teo_pending_high", "message": "No reconozco este cargo"},
    )
    # Teo's charge needs Teo's session.
    assert again.status_code == 404
    teo = login(client, "teo")
    teo_case = client.post(
        "/cases",
        headers=teo,
        json={"transaction_key": "tx_teo_pending_high", "message": "No reconozco este cargo"},
    ).json()
    failed = client.post(
        f"/cases/{teo_case['case_id']}/actions",
        headers=teo,
        json={"action": "confirm_block"},
    ).json()
    assert "No pude confirmar" in failed["reply"]
    assert "Bloqueé" not in failed["reply"]


def test_missing_features_are_review_never_low(client: TestClient) -> None:
    seen: list[str] = []

    class Spy(ScriptedTriage):
        def score(self, row: dict[str, object], config: object) -> object:
            seen.append(str(row.get("transaction_key")))
            return super().score(row, config)  # type: ignore[arg-type]

    client.app.state.engine.triage = Spy({"tx_maria_nofeat": "low"})
    config = client.app.state.thresholds.get()
    fallback = fallback_score(
        {"fraud_score": 6, "transaction_status": "Approved"},
        config,
    )
    assert fallback.band == "review"
    assert fallback.band != "low"
    headers = login(client, "maria")
    opened = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_nofeat", "message": "No reconozco este cargo"},
    ).json()
    assert opened["case_type"] == "triage"
    assert opened["actions"] == []
    assert "persona" in opened["reply"]
    assert "tx_maria_nofeat" not in seen
    current = [
        row
        for row in client.app.state.ops.current_audit_cases()
        if row["case_id"] == opened["case_id"]
    ]
    assert current[0]["decision"] == "handoff"
    assert "fallback_used" in current[0]["guardrail_flags"]


def test_low_duplicate_review_and_portuguese(client: TestClient) -> None:
    headers = login(client, "maria")
    low = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_low", "message": "No reconozco este cargo"},
    ).json()
    assert any(action["id"] == "recognize" for action in low["actions"])
    duplicate = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_dup_b", "message": "No reconozco este cargo"},
    ).json()
    assert duplicate["case_type"] == "duplicate_synthetic"
    assert "SINTÉTICO" in duplicate["reply"]
    review = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_review", "message": "No reconozco este cargo"},
    ).json()
    assert review["actions"] == []
    assert "bloquear la tarjeta" not in review["reply"].lower() or "No ofrecemos" in review["reply"]
    translated = {"text": "Não reconheço esta cobrança", "translated": True}
    assert translated["translated"] is True
    portuguese = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "tx_maria_pending", "message": translated["text"]},
    ).json()
    assert portuguese["language"] == "pt"
    assert "pendente" in portuguese["reply"]
    assert portuguese["actions"][0]["label"] == "Continuo sem reconhecer esta cobrança"


def test_customer_times_include_tijuana_and_hide_is_fraud(client: TestClient) -> None:
    utc = datetime(2026, 1, 15, 18, 0, tzinfo=UTC)
    assert present_time(utc, "America/Tijuana", "Mexico", "es")["abbreviation"] == "PST"
    assert "10:00" in present_time(utc, "America/Tijuana", "Mexico", "es")["label"]
    assert "12:00" in present_time(utc, "America/Mexico_City", "Mexico", "es")["label"]
    assert present_time(utc, "America/Mexico_City", "Mexico", "es")["abbreviation"] == "CST"
    assert (
        "UTC-3"
        in present_time(utc, "America/Argentina/Buenos_Aires", "Argentina", "es")["abbreviation"]
    )
    assert "UTC-5" in present_time(utc, "America/Bogota", "Colombia", "es")["abbreviation"]
    assert "is_fraud" not in TRANSACTION_COLUMNS

    teo = client.get("/api/transactions", headers=login(client, "teo")).json()
    home = next(row for row in teo["transactions"] if row["transaction_key"] == "tx_teo_home")
    assert "10:00" in home["local_time"]
    assert home["abbreviation"] == "PST"
    assert home["customer_tz"] == "America/Tijuana"
    assert "is_fraud" not in home

    camilo = client.get("/api/transactions", headers=login(client, "camilo")).json()
    abroad = next(
        row for row in camilo["transactions"] if row["transaction_key"] == "tx_camilo_abroad"
    )
    assert "13:00" in abroad["local_time"]
    assert abroad["abbreviation"] == "UTC-5"
    assert abroad["transaction_city"] == "Houston"

    maria = login(client, "maria")
    hidden = client.post(
        "/cases",
        headers=maria,
        json={"transaction_key": "tx_ana_home", "message": "No reconozco este cargo"},
    )
    assert hidden.status_code == 404


def test_lucia_sqlite_duplicate_scores_low(client: TestClient) -> None:
    import numpy as np
    import pandas as pd

    from app.bank.fixture import build_rows
    from triage.score import band_of, score_raw

    headers = login(client, "lucia")
    listed = client.get("/api/transactions", headers=headers).json()
    keys = {row["transaction_key"] for row in listed["transactions"]}
    assert {"tx_lucia_source", "SYN_0112_A", "SYN_0112_B"} <= keys
    pair = client.app.state.bank.get_duplicate("ck_mx_lucia", "SYN_0112_A")
    assert pair is not None
    assert pair.source_transaction_key == "tx_lucia_source"
    assert pair.other_transaction_key == "SYN_0112_B"
    assert client.app.state.bank.get_duplicate("ck_mx_lucia", "tx_lucia_source") is None

    seen: list[object] = []

    class Spy(ScriptedTriage):
        def score(self, row: dict[str, object], config: object) -> object:
            seen.append(row.get("fraud_score"))
            return super().score(row, config)  # type: ignore[arg-type]

    client.app.state.engine.triage = Spy({"SYN_0112_A": "low", "SYN_0112_B": "low"})
    opened = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": "SYN_0112_A", "message": "No reconozco este cargo"},
    ).json()
    assert opened["case_type"] == "duplicate_synthetic"
    assert "SINTÉTICO" in opened["reply"]
    assert "12:00" in opened["reply"]
    assert "12:10" in opened["reply"]
    source = client.app.state.bank.get_features("ck_mx_lucia", "tx_lucia_source")
    assert source is not None
    assert float(str(source["fraud_score"])) == 2.0
    assert seen == [1.0]

    _transactions, features, _duplicates = build_rows()
    feature = next(row for row in features if row["transaction_key"] == "tx_lucia_source")
    raw = score_raw(pd.DataFrame([feature]))
    assert band_of(raw, np.array([feature["fraud_score"]]))[0] == "low"
