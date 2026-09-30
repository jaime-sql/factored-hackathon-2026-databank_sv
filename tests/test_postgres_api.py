"""Postgres integration. Skipped unless TEST_DATABASE_URL points at app_rw.

The database is expected to already have migrations/001_app_schema.sql applied.
Persona maria signs CUS_75764d8a8e3d956f3320. That customer has tx_pg_high,
tx_pg_pending, tx_pg_low (fraud_features), and a SYN_0238_A / SYN_0238_B pair
whose source TXN_7d7509adf36aac31539d is a real charge outside the pair.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from app.auth.session import read_customer
from app.config import Settings
from app.db import connect_app
from app.main import create_app
from app.triage_model import ScriptedTriage
from tests.conftest import login

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is not set",
)

MARIA = "CUS_75764d8a8e3d956f3320"
SOURCE = "TXN_7d7509adf36aac31539d"

_PII_MARKERS = (
    "ck_mx_maria",
    "ck_ar_ana",
    "ck_co_camilo",
    "ck_mx_teo",
    MARIA,
    "CUS_bea1a374f5bcbe2b4b20",
    "CUS_b202620b1dbf4256f447",
    "CUS_e6543f8446563b61c837",
    "CUS_54f100f5046beb356091",
    "ck_mx_lucia",
    "SYN_0112",
    "tx_pg_",
    "SYN_0238",
    SOURCE,
    "customer_key",
    "transaction_key",
    "merchant_name",
    "Farmacia Norte",
    "Duplicado Demo",
    "@",
)


def _assert_ok(response: object, label: str) -> dict[str, object]:
    status = getattr(response, "status_code")
    body = getattr(response, "text")
    assert status < 500, f"{label} returned {status}: {body}"
    assert status == 200, f"{label} returned {status}: {body}"
    payload = response.json()  # type: ignore[attr-defined]
    assert isinstance(payload, dict)
    return payload


@pytest.fixture
def pg_client() -> object:
    settings = Settings(
        environment="local",
        database_url=os.environ["TEST_DATABASE_URL"],
        bank_db_path="",
        ops_db_path="",
        eval_runner_token="runner-secret",
        session_secret="test-session-secret-value",
        demo_agent_token="demo-agent-local",
        llm_provider="template",
    )
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        client.app.state.engine.triage = ScriptedTriage(
            {"tx_pg_low": "low", "SYN_0238_A": "low", "SYN_0238_B": "low"}
        )
        yield client


def test_connect_app_uses_app_rw_without_parameterized_set() -> None:
    with connect_app(os.environ["TEST_DATABASE_URL"]) as conn:
        role = conn.execute("SELECT current_user AS role_name").fetchone()
        timeout = conn.execute("SHOW statement_timeout").fetchone()
        assert role is not None
        assert role["role_name"] == "app_rw"
        assert timeout is not None
        assert timeout["statement_timeout"] == "15s"


def test_postgres_endpoints_do_not_500(pg_client: TestClient) -> None:
    headers = login(pg_client, "maria")
    agent = {"Authorization": "Bearer demo-agent-local"}

    personas = _assert_ok(pg_client.get("/api/personas"), "personas")
    maria = next(row for row in personas["personas"] if row["id"] == "maria")  # type: ignore[index]
    assert maria["segment"] == "Basic"
    assert maria["note"] == "Challenge data customer"
    lucia = next(row for row in personas["personas"] if row["id"] == "lucia")  # type: ignore[index]
    assert lucia["segment"] == "Basic"
    assert lucia["tz"] == "America/Mexico_City"
    assert lucia["country"] == "Mexico"
    assert lucia["note"] == "Challenge data customer, duplicate charge"
    lucia_session = pg_client.post("/api/session", json={"persona": "lucia"})
    assert lucia_session.status_code == 200
    signed = read_customer("test-session-secret-value", lucia_session.json()["token"])
    assert signed == "CUS_54f100f5046beb356091"

    listed = _assert_ok(pg_client.get("/api/transactions", headers=headers), "transactions")
    keys = {row["transaction_key"] for row in listed["transactions"]}  # type: ignore[index]
    assert {"tx_pg_high", "tx_pg_pending", "tx_pg_low", "SYN_0238_A", "SYN_0238_B", SOURCE} <= keys
    assert "is_fraud" not in json.dumps(listed)

    high = _assert_ok(
        pg_client.post(
            "/cases",
            headers=headers,
            json={"transaction_key": "tx_pg_high", "message": "No reconozco este cargo"},
        ),
        "open high case",
    )
    high_id = str(high["case_id"])
    _assert_ok(pg_client.get(f"/cases/{high_id}", headers=headers), "get high case")
    _assert_ok(
        pg_client.post(
            f"/cases/{high_id}/actions",
            headers=headers,
            json={"action": "confirm_block"},
        ),
        "confirm block",
    )

    pending = _assert_ok(
        pg_client.post(
            "/cases",
            headers=headers,
            json={"transaction_key": "tx_pg_pending", "message": "No reconozco este cargo"},
        ),
        "open pending case",
    )
    _assert_ok(
        pg_client.post(
            f"/cases/{pending['case_id']}/actions",
            headers=headers,
            json={"action": "contest"},
        ),
        "contest pending",
    )

    low = _assert_ok(
        pg_client.post(
            "/cases",
            headers=headers,
            json={"transaction_key": "tx_pg_low", "message": "No reconozco este cargo"},
        ),
        "open low case",
    )
    _assert_ok(
        pg_client.post(
            f"/cases/{low['case_id']}/actions",
            headers=headers,
            json={"action": "recognize"},
        ),
        "recognize low",
    )

    pair = pg_client.app.state.bank.get_duplicate(MARIA, "SYN_0238_A")
    assert pair is not None
    assert pair.customer_key == MARIA
    assert pair.source_transaction_key == SOURCE
    assert pair.other_transaction_key == "SYN_0238_B"
    other = pg_client.app.state.bank.get_duplicate(MARIA, "SYN_0238_B")
    assert other is not None
    assert other.other_transaction_key == "SYN_0238_A"
    assert other.source_transaction_key == SOURCE

    duplicate = _assert_ok(
        pg_client.post(
            "/cases",
            headers=headers,
            json={"transaction_key": "SYN_0238_A", "message": "No reconozco este cargo"},
        ),
        "open duplicate case",
    )
    assert duplicate["case_type"] == "duplicate_synthetic"
    reply = str(duplicate["reply"])
    assert "SINTÉTICO" in reply
    assert "12:00" in reply
    assert "12:10" in reply
    assert "09:00" not in reply
    _assert_ok(
        pg_client.post(
            f"/cases/{duplicate['case_id']}/actions",
            headers=headers,
            json={"action": "open_dispute"},
        ),
        "dispute duplicate",
    )

    queue = _assert_ok(pg_client.get("/api/handoff", headers=agent), "handoff queue")
    assert queue["queue"]  # type: ignore[index]
    case_id = str(queue["queue"][0]["case_id"])  # type: ignore[index]
    _assert_ok(pg_client.get(f"/api/handoff/{case_id}", headers=agent), "handoff detail")
    _assert_ok(pg_client.post(f"/api/handoff/{case_id}/claim", headers=agent), "claim handoff")

    exported = pg_client.get("/audit/export", headers=agent)
    assert exported.status_code < 500, exported.text
    assert exported.status_code == 200, exported.text
    assert "audit_id" in exported.text

    metrics = _assert_ok(pg_client.get("/api/metrics"), "metrics")
    blob = json.dumps(metrics)
    for marker in _PII_MARKERS:
        assert marker not in blob
    assert "k1_volume" in metrics
    assert "customer_key" not in metrics
