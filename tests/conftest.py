from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.triage_model import ScriptedTriage


@pytest.fixture
def client(tmp_path: object) -> object:
    root = tmp_path  # type: ignore[attr-defined]
    settings = Settings(
        environment="local",
        bank_db_path=str(root / "bank.sqlite"),
        ops_db_path=str(root / "ops.sqlite"),
        database_url="",
        eval_runner_token="runner-secret",
        session_secret="test-session-secret-value",
        demo_agent_token="demo-agent-local",
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        test_client.app.state.engine.triage = ScriptedTriage(
            {
                "tx_maria_low": "low",
                "tx_maria_dup_a": "low",
                "tx_maria_dup_b": "low",
                "tx_camilo_abroad": "low",
                "tx_ana_home": "low",
                "tx_teo_home": "low",
                "tx_camilo_home": "low",
                "tx_maria_home": "low",
                "tx_lucia_source": "low",
                "SYN_0112_A": "low",
                "SYN_0112_B": "low",
            }
        )
        yield test_client


def login(client: TestClient, persona: str) -> dict[str, str]:
    response = client.post("/api/session", json={"persona": persona})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}
