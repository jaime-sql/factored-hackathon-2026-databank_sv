"""Agent queue cards, the packet view, and the queue-only judge token."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.i18n import handoff_reason_label, mask_merchant
from app.main import create_app
from tests.conftest import login

ROOT = Path(__file__).resolve().parents[1]
JUDGE = "judge-demo-token"


def test_mask_and_reason_labels() -> None:
    assert mask_merchant("Tienda Don José") == "T••••• D•• J•••"
    assert mask_merchant("Uber") == "U•••"
    assert mask_merchant("categoría Food") == "c•••••••• F•••"
    assert mask_merchant("Comercio no identificado") == "C••••••• n• i•••••••••••"
    assert (
        handoff_reason_label(
            "es",
            "customer_requested_human",
            band="low",
            case_type="triage",
            synthetic=False,
            card_blocked=False,
        )
        == "Cliente pidió una persona (riesgo bajo)"
    )
    assert (
        handoff_reason_label(
            "pt",
            "fraud_model",
            band="review",
            case_type="duplicate_synthetic",
            synthetic=True,
            card_blocked=False,
        )
        == "Possível duplicado"
    )


def _open(client: TestClient, headers: dict[str, str], key: str, message: str) -> dict[str, object]:
    response = client.post(
        "/cases",
        headers=headers,
        json={"transaction_key": key, "message": message},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_queue_cards_and_packet_view(client: TestClient) -> None:
    headers = login(client, "maria")
    review = _open(client, headers, "tx_maria_review", "No reconozco este cargo")
    low = _open(client, headers, "tx_maria_low", "No reconozco este cargo")
    disputed = client.post(
        f"/cases/{low['case_id']}/actions",
        headers=headers,
        json={"action": "open_dispute"},
    )
    assert disputed.status_code == 200, disputed.text
    pending = _open(client, headers, "tx_maria_pending", "No reconozco este cargo")
    contested = client.post(
        f"/cases/{pending['case_id']}/actions",
        headers=headers,
        json={"action": "contest"},
    )
    assert contested.status_code == 200, contested.text
    high = _open(client, headers, "tx_maria_pending_high", "No reconozco este cargo")
    blocked = client.post(
        f"/cases/{high['case_id']}/actions",
        headers=headers,
        json={"action": "confirm_block"},
    )
    assert blocked.status_code == 200, blocked.text
    portuguese = _open(client, headers, "tx_maria_nofeat", "Não reconheço esta cobrança")

    agent = {"Authorization": "Bearer demo-agent-local"}
    queue = client.get("/api/handoff", headers=agent)
    assert queue.status_code == 200, queue.text
    by_id = {item["case_id"]: item for item in queue.json()["queue"]}
    assert by_id[str(review["case_id"])]["reason_label"] == "Modelo: revisión"
    assert by_id[str(review["case_id"])]["band"] == "review"
    assert "MXN" in by_id[str(review["case_id"])]["amount"]
    assert by_id[str(review["case_id"])]["merchant"] == "T••••• D•• J•••"
    assert "12:00" in by_id[str(review["case_id"])]["local_time"]
    assert by_id[str(low["case_id"])]["reason_label"] == "Cliente pidió una persona (riesgo bajo)"
    assert by_id[str(low["case_id"])]["band"] == "low"
    assert (
        by_id[str(pending["case_id"])]["reason_label"] == "Cliente impugnó explicación (pendiente)"
    )
    assert by_id[str(high["case_id"])]["reason_label"] == "Riesgo alto: tarjeta bloqueada"
    assert by_id[str(portuguese["case_id"])]["reason_label"] == "Modelo: revisão"
    generic = "Revisar el cargo con una persona. No bloquear la tarjeta"
    assert all(generic not in item["reason_label"] for item in by_id.values())

    detail = client.get(f"/api/handoff/{high['case_id']}", headers=agent)
    assert detail.status_code == 200, detail.text
    view = detail.json()["view"]
    assert view["band"] == "high"
    assert view["model_version"]
    assert view["threshold_crossed"].startswith("fraud_score > 30")
    assert "MXN" in view["amount"]
    assert view["merchant"]
    assert view["local_time"]
    assert view["customer_tz"] == "America/Mexico_City"
    assert view["utc"]
    assert {"name": "block_card", "verification_status": "verified"} in view["actions_taken"]
    assert view["reason_label"] == "Riesgo alto: tarjeta bloqueada"
    assert view["recommended_next_step"]
    assert "is_fraud" not in detail.text

    review_detail = client.get(f"/api/handoff/{review['case_id']}", headers=agent)
    review_view = review_detail.json()["view"]
    assert review_view["threshold_crossed"].startswith("score >= ")
    assert review_view["model_version"].startswith("lgbm:")
    assert review_view["model_risk_score"] is not None


def test_packet_enums_stay_raw_in_audit_api_and_export(client: TestClient) -> None:
    headers = login(client, "maria")
    opened = _open(client, headers, "tx_maria_pending_high", "No reconozco este cargo")
    blocked = client.post(
        f"/cases/{opened['case_id']}/actions",
        headers=headers,
        json={"action": "confirm_block"},
    )
    assert blocked.status_code == 200, blocked.text
    case_id = str(opened["case_id"])
    agent = {"Authorization": "Bearer demo-agent-local"}
    detail = client.get(f"/api/handoff/{case_id}", headers=agent)
    assert detail.status_code == 200, detail.text
    view = detail.json()["view"]
    assert view["band"] == "high"
    assert {"name": "block_card", "verification_status": "verified"} in view["actions_taken"]
    for translated in ("Alto", "Bloqueo de tarjeta verificado", "Traspaso verificado"):
        assert translated not in detail.text

    ops = client.app.state.ops
    stored = ops.get_handoff(case_id)
    assert stored is not None
    packet = stored["packet"]
    assert packet["triage"]["band"] == "high"
    assert {"name": "block_card", "verification_status": "verified"} in packet["actions_taken"]
    events = ops.list_events(case_id)
    pairs = {(row["name"], row["verification_status"]) for row in events}
    assert ("block_card", "verified") in pairs
    assert ("handoff", "verified") in pairs

    current = [row for row in ops.current_audit_cases() if row["case_id"] == case_id]
    assert current
    assert all(row["decision"] == "handoff" for row in current if row.get("decision"))
    underlying = ops.execute(
        f"SELECT decision FROM {ops._table('audit_case')} WHERE case_id = ?",
        (case_id,),
    )
    assert underlying
    decisions = {row["decision"] for row in underlying}
    assert "handoff" in decisions
    assert decisions <= {None, "handoff"}

    exported = client.get("/audit/export", headers=agent)
    assert exported.status_code == 200, exported.text
    assert "handoff" in exported.text
    for translated in ("Alto", "Bloqueo de tarjeta verificado", "Traspaso verificado"):
        assert translated not in exported.text

    trail = client.get(f"/api/cases/{case_id}/trail", headers=agent)
    assert trail.status_code == 200, trail.text
    steps = trail.json()["steps"]
    assert any(step.get("band") == "high" for step in steps)
    assert any(
        step.get("action") == "handoff" and step.get("verification") == "verified" for step in steps
    )
    assert "Traspaso verificado" not in trail.text


def test_agent_console_script_renders_packet() -> None:
    completed = subprocess.run(
        ["node", "tests/test_agent_console.js"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def _judge_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        environment="local",
        bank_db_path=str(tmp_path / "bank.sqlite"),
        ops_db_path=str(tmp_path / "ops.sqlite"),
        database_url="",
        eval_runner_token="runner-secret",
        session_secret="test-session-secret-value",
        demo_agent_token="demo-agent-local",
        demo_judge_token=JUDGE,
    )
    app = create_app(settings)
    client = TestClient(app)
    client.__enter__()
    from app.triage_model import ScriptedTriage

    client.app.state.engine.triage = ScriptedTriage(
        {"tx_maria_low": "low", "tx_maria_review": "review"}
    )
    return client


def test_judge_token_queue_only(tmp_path: Path, client: TestClient) -> None:
    denied = client.get("/api/handoff", headers={"Authorization": f"Bearer {JUDGE}"})
    assert denied.status_code == 401

    judge_client = _judge_client(tmp_path)
    try:
        headers = login(judge_client, "maria")
        opened = _open(judge_client, headers, "tx_maria_review", "No reconozco este cargo")
        judge = {"Authorization": f"Bearer {JUDGE}"}
        admin = {"Authorization": "Bearer demo-agent-local"}
        queue = judge_client.get("/api/handoff", headers=judge)
        assert queue.status_code == 200, queue.text
        assert queue.json()["queue"]
        detail = judge_client.get(f"/api/handoff/{opened['case_id']}", headers=judge)
        assert detail.status_code == 200, detail.text
        assert detail.json()["view"]["reason_label"] == "Modelo: revisión"
        claimed = judge_client.post(f"/api/handoff/{opened['case_id']}/claim", headers=judge)
        assert claimed.status_code == 200, claimed.text
        resolved = judge_client.post(
            f"/api/handoff/{opened['case_id']}/resolve",
            headers=judge,
            json={"note": "visto"},
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "resolved"
        exported = judge_client.get("/audit/export", headers=judge)
        assert exported.status_code == 403
        config = judge_client.get("/api/auth/config", headers=judge)
        assert config.status_code == 403
        admin_export = judge_client.get("/audit/export", headers=admin)
        assert admin_export.status_code == 200, admin_export.text
        public_config = judge_client.get("/api/auth/config")
        assert public_config.status_code == 200
        assert "demo_judge" not in public_config.text
    finally:
        judge_client.__exit__(None, None, None)
