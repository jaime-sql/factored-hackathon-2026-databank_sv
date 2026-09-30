from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_matches_healthz(client: TestClient) -> None:
    health = client.get("/health")
    healthz = client.get("/healthz")
    assert health.status_code == 200
    assert healthz.status_code == 200
    assert health.json() == healthz.json()
    body = health.json()
    assert body["status"] == "ok"
    assert body["bank"] == "sqlite"
    assert body["ops"] == "sqlite"
    assert "llm" in body
