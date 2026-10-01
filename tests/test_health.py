from __future__ import annotations

from fastapi.testclient import TestClient


def test_favicon(client: TestClient) -> None:
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")
    assert response.content.startswith(b"\x00\x00\x01\x00")


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
    assert body["migrations_ok"] is True
    assert "llm" in body
