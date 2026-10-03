"""Language toggle copy comes from the i18n catalog, including statuses and months."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.bank.fixture import build_rows
from app.i18n import (
    category_label,
    money,
    place_label,
    transaction_status_label,
    transaction_type_label,
    ui_copy,
)
from app.timeutil import present_time
from tests.conftest import login

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_statuses_and_months(client: TestClient) -> None:
    catalog = client.get("/api/i18n").json()
    es = catalog["es"]
    pt = catalog["pt"]
    assert es["client_lede"].startswith("Un cargo a la vez")
    assert pt["client_lede"].startswith("Uma cobrança de cada vez")
    assert es["status"] == {
        "Approved": "Aprobado",
        "Pending": "Pendiente",
        "Reversed": "Reversado",
        "Declined": "Rechazado",
    }
    assert pt["status"] == {
        "Approved": "Aprovado",
        "Pending": "Pendente",
        "Reversed": "Estornado",
        "Declined": "Recusado",
    }
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
    assert "offline" not in spanish_metrics["eval_toggle_label"].lower()
    assert "HIGH" not in spanish_metrics["eval_toggle_label"]


def test_statuses_types_amounts_and_foreign_country(client: TestClient) -> None:
    mapping = json.loads(
        (ROOT / "triage/artifacts/category_mappings.json").read_text(encoding="utf-8")
    )
    fixture_statuses = {str(row["transaction_status"]) for row in build_rows()[0]}
    required = fixture_statuses | {"Declined"}
    for status in required:
        spanish = transaction_status_label("es", status)
        portuguese = transaction_status_label("pt", status)
        assert spanish != status
        assert portuguese != status
        assert status not in spanish
        assert status not in portuguese
    assert transaction_status_label("es", "Declined") == "Rechazado"
    assert transaction_status_label("pt", "Declined") == "Recusado"
    for kind in mapping["transaction_type"]:
        assert transaction_type_label("es", kind) != kind
        assert transaction_type_label("pt", kind) != kind
    assert money(1645.6, "USD", "Mexico") == "US$1,645.60"
    assert money(1645.6, "USD", "MX") == "US$1,645.60"
    assert money(1645.6, "USD", "Colombia") == "US$ 1.645,60"
    assert money(1645.6, "USD", "Argentina") == "US$ 1.645,60"
    assert money(1645.6, "USD", "Spain") == "US$ 1.645,60"
    assert money(1645.6, "USD", "Brazil") == "US$ 1.645,60"
    assert money(220, "MXN", "Mexico") == "MXN220.00"
    assert money(220, "MXN", "Colombia") == "MXN 220,00"
    assert place_label("Valencia", "Spain", "Mexico", "es") == "Valencia, España"
    assert place_label("Valencia", "Spain", "Mexico", "pt") == "Valencia, Espanha"
    assert place_label("Valencia", "", "Mexico", "es") == "Valencia"
    assert place_label("Valencia", "Spain", "Spain", "es") == "Valencia"
    assert place_label("", "Spain", "Mexico", "pt") == "Espanha"
    assert place_label("", "", "Mexico", "es") == ""

    headers = login(client, "camilo")
    spanish = client.get("/api/transactions?language=es", headers=headers).json()
    portuguese = client.get("/api/transactions?language=pt", headers=headers).json()
    abroad = next(
        row for row in spanish["transactions"] if row["transaction_key"] == "tx_camilo_abroad"
    )
    home = next(
        row for row in spanish["transactions"] if row["transaction_key"] == "tx_camilo_home"
    )
    abroad_pt = next(
        row for row in portuguese["transactions"] if row["transaction_key"] == "tx_camilo_abroad"
    )
    assert abroad["transaction_country"] == "USA"
    assert abroad["place"] == "Houston, Estados Unidos"
    assert home["place"] == "Bogotá"
    assert "," not in home["place"]
    assert abroad_pt["place"] == "Houston, Estados Unidos"
    assert "US$" in abroad["amount_label"]
    assert abroad["amount_label"].endswith("28,00")
    parts = (
        abroad["local_time"],
        abroad["place"],
        abroad["amount_label"],
        abroad["status_label"],
    )
    joined = " · ".join(part for part in parts if str(part or "").strip())
    assert "· ·" not in joined


def test_every_category_has_spanish_and_portuguese() -> None:
    mapping_path = ROOT / "triage/artifacts/category_mappings.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    found = set(mapping["transaction_category"]) | set(mapping["merchant_category"])
    for table in build_rows():
        for row in table:
            if not isinstance(row, dict):
                continue
            for key in ("transaction_category", "merchant_category"):
                value = str(row.get(key) or "").strip()
                if value:
                    found.add(value)
    assert found
    for category in sorted(found):
        spanish = category_label("es", category)
        portuguese = category_label("pt", category)
        assert spanish
        assert portuguese
        assert spanish != category
        assert portuguese != category
    assert category_label("es", "Entertainment") == "Entretenimiento"
    assert category_label("pt", "Entertainment") == "Entretenimento"
    assert category_label("pt", "Entretenimiento") == "Entretenimento"


def test_page_catalog_is_generated_from_ui_catalog() -> None:
    from app.i18n import catalog_script, write_catalog_script

    path = write_catalog_script()
    script = path.read_text(encoding="utf-8")
    assert script == catalog_script()
    assert script.startswith("// Generated from app.i18n.ui_catalog. Do not edit.\n")
    assert "globalThis.HD_CATALOG=" in script


def test_locale_toggle_on_each_page() -> None:
    completed = subprocess.run(
        ["node", "tests/test_locale.js"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_demo_buttons_run_real_charges_and_scroll_to_why() -> None:
    completed = subprocess.run(
        ["node", "tests/test_demos.js"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
