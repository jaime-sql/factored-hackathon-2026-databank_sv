"""Language toggle copy comes from the i18n catalog, including statuses and months."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.i18n import ui_copy
from app.timeutil import present_time
from tests.conftest import login

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_statuses_and_months(client: TestClient) -> None:
    catalog = client.get("/api/i18n").json()
    es = catalog["es"]
    pt = catalog["pt"]
    assert es["client_lede"].startswith("Un cargo a la vez")
    assert pt["client_lede"].startswith("Uma cobrança de cada vez")
    assert es["status"] == {"Approved": "Aprobado", "Pending": "Pendiente", "Reversed": "Reversado"}
    assert pt["status"] == {"Approved": "Aprovado", "Pending": "Pendente", "Reversed": "Estornado"}
    assert es["months"][0] == "ene"
    assert pt["months"][0] == "jan"
    assert es["months"][4] == "may"
    assert pt["months"][4] == "mai"
    assert es["months"][5] == "jun"
    assert pt["months"][5] == "jun"
    assert es["months"][3] == "abr"
    assert pt["months"][3] == "abr"
    assert "Approved" not in es["status"].values()
    assert "seguro" not in pt["client_lede"].lower()
    may = datetime(2026, 5, 19, 18, 0, tzinfo=UTC)
    june = datetime(2026, 6, 10, 18, 0, tzinfo=UTC)
    april = datetime(2026, 4, 25, 18, 0, tzinfo=UTC)
    assert present_time(may, "America/Mexico_City", "Mexico", "es")["label"].startswith("19 may ")
    assert present_time(may, "America/Mexico_City", "Mexico", "pt")["label"].startswith("19 mai ")
    assert present_time(june, "America/Mexico_City", "Mexico", "es")["label"].startswith("10 jun ")
    assert present_time(june, "America/Mexico_City", "Mexico", "pt")["label"].startswith("10 jun ")
    assert present_time(april, "America/Mexico_City", "Mexico", "es")["label"].startswith("25 abr ")
    assert present_time(april, "America/Mexico_City", "Mexico", "pt")["label"].startswith("25 abr ")

    headers = login(client, "maria")
    spanish = client.get("/api/transactions?language=es", headers=headers).json()
    portuguese = client.get("/api/transactions?language=pt", headers=headers).json()
    pending = next(row for row in spanish["transactions"] if row["transaction_status"] == "Pending")
    pending_pt = next(
        row
        for row in portuguese["transactions"]
        if row["transaction_key"] == pending["transaction_key"]
    )
    assert " ene " in f" {pending['local_time']} "
    assert " jan " in f" {pending_pt['local_time']} "
    assert pending["status_label"] == "Pendiente"
    assert pending_pt["status_label"] == "Pendente"
    assert pending["transaction_status"] == "Pending"
    assert ui_copy("es")["queue_empty"].startswith("No hay casos")
    assert ui_copy("pt")["queue_failed"].startswith("Não foi possível")
    spanish_metrics = client.get("/api/metrics?language=es").json()
    portuguese_metrics = client.get("/api/metrics?language=pt").json()
    assert spanish_metrics["k5_handoff"]["display"] == "no definido"
    assert portuguese_metrics["k5_handoff"]["display"] == "não definido"
    assert "Demo sample" not in spanish_metrics["eval_toggle_label"]
    assert "not defined" not in str(spanish_metrics)


def test_locale_toggle_on_each_page() -> None:
    completed = subprocess.run(
        ["node", "tests/test_locale.js"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
