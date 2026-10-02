"""Small synthetic SQLite slice. Not real customer data.

The transactions table includes an is_fraud column on purpose. The repository
must never select it. Times are UTC ISO strings. customers.tz is always set,
including America/Tijuana.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.paths import project_root

FIXTURE_VERSION = "2026-09-30-lucia-dup"
UTC_STAMP = "2026-01-15T18:00:00+00:00"

PERSONAS: tuple[dict[str, str], ...] = (
    {
        "id": "ana",
        "customer_key": "ck_ar_ana",
        "bank_customer_key": "CUS_bea1a374f5bcbe2b4b20",
        "label": "Ana · Argentina",
        "country": "Argentina",
        "segment": "Basic",
        "accent": "rioplatense",
        "tz": "America/Argentina/Buenos_Aires",
        "note": "Synthetic persona",
    },
    {
        "id": "camilo",
        "customer_key": "ck_co_camilo",
        "bank_customer_key": "CUS_b202620b1dbf4256f447",
        "label": "Camilo · Barranquilla",
        "country": "Colombia",
        "segment": "Plus",
        "accent": "andino",
        "tz": "America/Bogota",
        "note": "Synthetic persona",
    },
    {
        "id": "maria",
        "customer_key": "ck_mx_maria",
        "bank_customer_key": "CUS_75764d8a8e3d956f3320",
        "label": "María · Ciudad de México",
        "country": "Mexico",
        "segment": "Basic",
        "accent": "centro",
        "tz": "America/Mexico_City",
        "note": "Synthetic persona",
    },
    {
        "id": "teo",
        "customer_key": "ck_mx_teo",
        "bank_customer_key": "CUS_e6543f8446563b61c837",
        "label": "Teo · Tijuana",
        "country": "Mexico",
        "segment": "Student",
        "accent": "noroeste",
        "tz": "America/Tijuana",
        "note": "Synthetic persona. MX is not Mexico City.",
    },
    {
        "id": "lucia",
        "customer_key": "ck_mx_lucia",
        "bank_customer_key": "CUS_54f100f5046beb356091",
        "label": "Lucía · Querétaro",
        "country": "Mexico",
        "segment": "Basic",
        "accent": "bajio",
        "tz": "America/Mexico_City",
        "note": "Synthetic persona, duplicate charge",
    },
)


def persona_first_name(customer_key: str) -> str:
    """First token of a demo persona label, or empty when the key is not a persona."""
    for row in PERSONAS:
        if customer_key not in {row["customer_key"], row["bank_customer_key"]}:
            continue
        label = row["label"].split("·", 1)[0].strip()
        token = label.split()[0] if label else ""
        if token and "[" not in token and "]" not in token:
            return token
        return ""
    return ""


def _features(tx: dict[str, object], customer: dict[str, str]) -> dict[str, object]:
    amount = float(str(tx["amount"]))
    local = datetime(2026, 1, 15, 18, 0, tzinfo=UTC)
    abroad = tx["transaction_country"] not in {"Mexico", "Colombia", "Argentina"}
    return {
        "transaction_key": tx["transaction_key"],
        "customer_key": customer["customer_key"],
        "amount": amount,
        "log_amount": math.log(amount),
        "amount_usd": tx["amount_usd"],
        "fraud_score": tx["fraud_score"],
        "local_hour": local.hour,
        "local_dow": local.isoweekday(),
        "is_night": 0,
        "is_weekend": 0,
        "is_cross_border": 1 if abroad else 0,
        "customer_tenure_days": 400,
        "product_tenure_days": 200,
        "prior_tx_count": 4,
        "prior_tx_count_1h": 0,
        "prior_tx_count_24h": 1,
        "prior_tx_count_7d": 2,
        "secs_since_prev_tx": 86_400,
        "prior_mean_amount_same_ccy": amount,
        "amount_to_prior_mean": 1.0,
        "prior_count_same_merchant": 0,
        "prior_cross_border_count_30d": 1 if abroad else 0,
        "currency": tx["currency"],
        "channel": tx["channel"],
        "transaction_type": tx["transaction_type"],
        "transaction_category": tx["transaction_category"],
        "merchant_category": tx["merchant_category"],
        "merchant_name": tx["merchant_name"],
        "transaction_country": tx["transaction_country"],
        "transaction_city": tx["transaction_city"],
        "product_type": tx["product_type"],
    }


def _tx(
    key: str,
    customer: dict[str, str],
    *,
    merchant: str,
    city: str,
    country: str,
    status: str,
    fraud_score: float | None,
    amount: float,
    currency: str,
    is_fraud_trap: int,
    category: str = "Food",
) -> dict[str, object]:
    return {
        "transaction_key": key,
        "customer_key": customer["customer_key"],
        "product_key": f"card_{customer['id']}",
        "product_type": "Tarjeta Débito",
        "transaction_type": "Purchase",
        "transaction_category": category,
        "currency": currency,
        "channel": "POS",
        "branch_id": "br_01",
        "merchant_name": merchant,
        "merchant_category": category,
        "transaction_country": country,
        "transaction_city": city,
        "transaction_status": status,
        "response_code": "00",
        "is_fraud": is_fraud_trap,
        "customer_country": customer["country"],
        "customer_segment": customer["segment"],
        "customer_accent": customer["accent"],
        "transaction_ts_utc": UTC_STAMP,
        "transaction_ts_local": "DO_NOT_DISPLAY",
        "process_date": "2026-01-15",
        "amount": amount,
        "amount_usd": round(amount / 20, 2) if currency == "MXN" else round(amount / 1000, 2),
        "fraud_score": fraud_score,
    }


def build_rows() -> tuple[
    list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]
]:
    by_id = {p["id"]: p for p in PERSONAS}
    ana, camilo, maria, teo = by_id["ana"], by_id["camilo"], by_id["maria"], by_id["teo"]
    lucia = by_id["lucia"]
    transactions = [
        _tx(
            "tx_ana_home",
            ana,
            merchant="Mercado Central",
            city="Buenos Aires",
            country="Argentina",
            status="Approved",
            fraud_score=2,
            amount=15000,
            currency="ARS",
            is_fraud_trap=0,
        ),
        _tx(
            "tx_camilo_home",
            camilo,
            merchant="Restaurante El Buen Sabor",
            city="Bogotá",
            country="Colombia",
            status="Approved",
            fraud_score=3,
            amount=45000,
            currency="COP",
            is_fraud_trap=0,
        ),
        _tx(
            "tx_camilo_abroad",
            camilo,
            merchant="Uber",
            city="Houston",
            country="USA",
            status="Approved",
            fraud_score=4,
            amount=28,
            currency="USD",
            is_fraud_trap=0,
            category="Transport",
        ),
        _tx(
            "tx_maria_home",
            maria,
            merchant="Super Ahorro",
            city="Ciudad de México",
            country="Mexico",
            status="Approved",
            fraud_score=2,
            amount=640,
            currency="MXN",
            is_fraud_trap=0,
        ),
        _tx(
            "tx_maria_pending",
            maria,
            merchant="Farmacia Salud",
            city="Ciudad de México",
            country="Mexico",
            status="Pending",
            fraud_score=5,
            amount=180,
            currency="MXN",
            is_fraud_trap=1,
            category="Health",
        ),
        _tx(
            "tx_maria_pending_30",
            maria,
            merchant="Tienda General",
            city="Ciudad de México",
            country="Mexico",
            status="Pending",
            fraud_score=30,
            amount=90,
            currency="MXN",
            is_fraud_trap=0,
        ),
        _tx(
            "tx_maria_pending_high",
            maria,
            merchant="Uber",
            city="Ciudad de México",
            country="Mexico",
            status="Pending",
            fraud_score=31,
            amount=220,
            currency="MXN",
            is_fraud_trap=0,
            category="Transport",
        ),
        _tx(
            "tx_maria_reversed",
            maria,
            merchant="Cine Premium",
            city="Ciudad de México",
            country="Mexico",
            status="Reversed",
            fraud_score=8,
            amount=160,
            currency="MXN",
            is_fraud_trap=0,
            category="Entertainment",
        ),
        _tx(
            "tx_maria_reversed_high",
            maria,
            merchant="Gasolinera Express",
            city="Ciudad de México",
            country="Mexico",
            status="Reversed",
            fraud_score=45,
            amount=800,
            currency="MXN",
            is_fraud_trap=1,
            category="Transport",
        ),
        _tx(
            "tx_maria_low",
            maria,
            merchant="Café Norte",
            city="Ciudad de México",
            country="Mexico",
            status="Approved",
            fraud_score=2,
            amount=75,
            currency="MXN",
            is_fraud_trap=0,
        ),
        _tx(
            "tx_maria_review",
            maria,
            merchant="Tienda Don José",
            city="Ciudad de México",
            country="Mexico",
            status="Approved",
            fraud_score=12,
            amount=1400,
            currency="MXN",
            is_fraud_trap=0,
        ),
        _tx(
            "tx_maria_nofeat",
            maria,
            merchant="Taller Centro",
            city="Ciudad de México",
            country="Mexico",
            status="Approved",
            fraud_score=6,
            amount=300,
            currency="MXN",
            is_fraud_trap=0,
        ),
        _tx(
            "tx_maria_dup_a",
            maria,
            merchant="Streaming Music",
            city="Ciudad de México",
            country="Mexico",
            status="Approved",
            fraud_score=3,
            amount=99,
            currency="MXN",
            is_fraud_trap=0,
            category="Entertainment",
        ),
        _tx(
            "tx_maria_dup_b",
            maria,
            merchant="Streaming Music",
            city="Ciudad de México",
            country="Mexico",
            status="Approved",
            fraud_score=3,
            amount=99,
            currency="MXN",
            is_fraud_trap=0,
            category="Entertainment",
        ),
        _tx(
            "tx_teo_home",
            teo,
            merchant="Taxi Seguro",
            city="Tijuana",
            country="Mexico",
            status="Approved",
            fraud_score=2,
            amount=120,
            currency="MXN",
            is_fraud_trap=0,
            category="Transport",
        ),
        _tx(
            "tx_teo_pending_high",
            teo,
            merchant="Ferretería",
            city="Tijuana",
            country="Mexico",
            status="Pending",
            fraud_score=31,
            amount=540,
            currency="MXN",
            is_fraud_trap=0,
        ),
        _tx(
            "tx_lucia_source",
            lucia,
            merchant="Centro Comercial",
            city="Querétaro",
            country="Mexico",
            status="Approved",
            fraud_score=2,
            amount=240,
            currency="MXN",
            is_fraud_trap=0,
            category="Food",
        ),
    ]
    # Shift the duplicate a few minutes so both times show. Keep the same UTC date.
    for tx in transactions:
        if tx["transaction_key"] == "tx_maria_dup_b":
            tx["transaction_ts_utc"] = "2026-01-15T18:04:00+00:00"
    features = []
    customers_by_key = {p["customer_key"]: p for p in PERSONAS}
    for tx in transactions:
        if (
            tx["transaction_status"] in {"Pending", "Reversed"}
            or tx["transaction_key"] == "tx_maria_nofeat"
        ):
            continue
        customer = customers_by_key[str(tx["customer_key"])]
        features.append(_features(tx, customer))
    duplicates = [
        {
            "case_id": "syn_dup_maria",
            "scenario": "double_swipe",
            "role": "original",
            "is_synthetic": 1,
            "seconds_after_original": 0,
            "source_transaction_key": "tx_maria_dup_a",
            "transaction_key": "tx_maria_dup_a",
            "customer_key": maria["customer_key"],
            "product_key": "card_maria",
            "product_type": "Tarjeta Débito",
            "transaction_ts_utc": UTC_STAMP,
            "transaction_ts_local": "DO_NOT_DISPLAY",
            "process_date": "2026-01-15",
            "transaction_type": "Purchase",
            "transaction_category": "Entertainment",
            "amount": 99,
            "currency": "MXN",
            "amount_usd": 5,
            "channel": "POS",
            "branch_id": "br_01",
            "merchant_name": "Streaming Music",
            "merchant_category": "Entertainment",
            "transaction_country": "Mexico",
            "transaction_city": "Ciudad de México",
            "transaction_status": "Approved",
            "response_code": "00",
            "is_fraud": "0",
            "fraud_score": 3,
            "customer_country": "MX",
            "customer_segment": "Basic",
            "customer_accent": "centro",
        },
        {
            "case_id": "syn_dup_maria",
            "scenario": "double_swipe",
            "role": "duplicate",
            "is_synthetic": 1,
            "seconds_after_original": 240,
            "source_transaction_key": "tx_maria_dup_a",
            "transaction_key": "tx_maria_dup_b",
            "customer_key": maria["customer_key"],
            "product_key": "card_maria",
            "product_type": "Tarjeta Débito",
            "transaction_ts_utc": "2026-01-15T18:04:00+00:00",
            "transaction_ts_local": "DO_NOT_DISPLAY",
            "process_date": "2026-01-15",
            "transaction_type": "Purchase",
            "transaction_category": "Entertainment",
            "amount": 99,
            "currency": "MXN",
            "amount_usd": 5,
            "channel": "POS",
            "branch_id": "br_01",
            "merchant_name": "Streaming Music",
            "merchant_category": "Entertainment",
            "transaction_country": "Mexico",
            "transaction_city": "Ciudad de México",
            "transaction_status": "Approved",
            "response_code": "00",
            "is_fraud": "0",
            "fraud_score": 3,
            "customer_country": "MX",
            "customer_segment": "Basic",
            "customer_accent": "centro",
        },
        _synthetic_charge(
            lucia,
            transaction_key="SYN_0112_A",
            role="original",
            seconds_after=0,
            when=UTC_STAMP,
        ),
        _synthetic_charge(
            lucia,
            transaction_key="SYN_0112_B",
            role="duplicate",
            seconds_after=600,
            when="2026-01-15T18:10:00+00:00",
        ),
    ]
    return transactions, features, duplicates


def _synthetic_charge(
    customer: dict[str, str],
    *,
    transaction_key: str,
    role: str,
    seconds_after: int,
    when: str,
) -> dict[str, object]:
    """SYN pair only. The source charge stays in transactions and is not a pair member."""
    return {
        "case_id": "syn_dup_lucia",
        "scenario": "true_duplicate",
        "role": role,
        "is_synthetic": 1,
        "seconds_after_original": seconds_after,
        "source_transaction_key": "tx_lucia_source",
        "transaction_key": transaction_key,
        "customer_key": customer["customer_key"],
        "product_key": "card_lucia",
        "product_type": "Tarjeta Débito",
        "transaction_ts_utc": when,
        "transaction_ts_local": "DO_NOT_DISPLAY",
        "process_date": "2026-01-15",
        "transaction_type": "Purchase",
        "transaction_category": "Food",
        "amount": 240,
        "currency": "MXN",
        "amount_usd": 12,
        "channel": "POS",
        "branch_id": "br_01",
        "merchant_name": "Centro Comercial",
        "merchant_category": "Food",
        "transaction_country": "Mexico",
        "transaction_city": "Querétaro",
        "transaction_status": "Approved",
        "response_code": "00",
        "is_fraud": "0",
        "fraud_score": 1,
        "customer_country": "Mexico",
        "customer_segment": "Basic",
        "customer_accent": "bajio",
    }


def feature_names() -> list[str]:
    payload = json.loads(
        (project_root() / "triage" / "artifacts" / "feature_list.json").read_text(encoding="utf-8")
    )
    names = payload["features"]
    if not isinstance(names, list) or any(name == "is_fraud" for name in names):
        raise RuntimeError("feature list is invalid")
    return [str(name) for name in names]


def init_bank(path: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        with sqlite3.connect(destination) as conn:
            try:
                row = conn.execute(
                    "SELECT value FROM meta WHERE key = 'fixture_version'"
                ).fetchone()
            except sqlite3.Error:
                row = None
        if row and row[0] == FIXTURE_VERSION:
            return
        destination.unlink()
    transactions, features, duplicates = build_rows()
    names = feature_names()
    with sqlite3.connect(destination) as conn:
        conn.executescript(
            """
            CREATE TABLE customers (
              customer_key TEXT PRIMARY KEY,
              customer_country TEXT NOT NULL,
              customer_segment TEXT NOT NULL,
              customer_accent TEXT,
              slice_reason TEXT,
              tz TEXT NOT NULL
            );
            CREATE TABLE transactions (
              transaction_key TEXT PRIMARY KEY,
              customer_key TEXT NOT NULL,
              product_key TEXT,
              product_type TEXT,
              transaction_type TEXT,
              transaction_category TEXT,
              currency TEXT,
              channel TEXT,
              branch_id TEXT,
              merchant_name TEXT,
              merchant_category TEXT,
              transaction_country TEXT,
              transaction_city TEXT,
              transaction_status TEXT,
              response_code TEXT,
              is_fraud INTEGER,
              customer_country TEXT,
              customer_segment TEXT,
              customer_accent TEXT,
              transaction_ts_utc TEXT,
              transaction_ts_local TEXT,
              process_date TEXT,
              amount REAL,
              amount_usd REAL,
              fraud_score REAL
            );
            CREATE TABLE synthetic_duplicates (
              case_id TEXT,
              scenario TEXT,
              role TEXT,
              is_synthetic INTEGER,
              seconds_after_original INTEGER,
              source_transaction_key TEXT,
              transaction_key TEXT,
              customer_key TEXT,
              product_key TEXT,
              product_type TEXT,
              transaction_ts_utc TEXT,
              transaction_ts_local TEXT,
              process_date TEXT,
              transaction_type TEXT,
              transaction_category TEXT,
              amount REAL,
              currency TEXT,
              amount_usd REAL,
              channel TEXT,
              branch_id TEXT,
              merchant_name TEXT,
              merchant_category TEXT,
              transaction_country TEXT,
              transaction_city TEXT,
              transaction_status TEXT,
              response_code TEXT,
              is_fraud TEXT,
              fraud_score REAL,
              customer_country TEXT,
              customer_segment TEXT,
              customer_accent TEXT
            );
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            """
        )
        feature_cols = ", ".join(
            f"{name} {'REAL' if name in _NUMERIC else 'TEXT'}" for name in names
        )
        conn.execute(
            f"CREATE TABLE fraud_features (transaction_key TEXT PRIMARY KEY, customer_key TEXT NOT NULL, {feature_cols})"
        )
        for persona in PERSONAS:
            conn.execute(
                "INSERT INTO customers (customer_key, customer_country, customer_segment, customer_accent, slice_reason, tz) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    persona["customer_key"],
                    persona["country"],
                    persona["segment"],
                    persona["accent"],
                    "synthetic_fixture",
                    persona["tz"],
                ),
            )
        tx_columns = [
            "transaction_key",
            "customer_key",
            "product_key",
            "product_type",
            "transaction_type",
            "transaction_category",
            "currency",
            "channel",
            "branch_id",
            "merchant_name",
            "merchant_category",
            "transaction_country",
            "transaction_city",
            "transaction_status",
            "response_code",
            "is_fraud",
            "customer_country",
            "customer_segment",
            "customer_accent",
            "transaction_ts_utc",
            "transaction_ts_local",
            "process_date",
            "amount",
            "amount_usd",
            "fraud_score",
        ]
        placeholders = ", ".join("?" for _ in tx_columns)
        conn.executemany(
            f"INSERT INTO transactions ({', '.join(tx_columns)}) VALUES ({placeholders})",
            [tuple(tx[col] for col in tx_columns) for tx in transactions],
        )
        feat_columns = ["transaction_key", "customer_key", *names]
        conn.executemany(
            f"INSERT INTO fraud_features ({', '.join(feat_columns)}) VALUES ({', '.join('?' for _ in feat_columns)})",
            [tuple(row[col] for col in feat_columns) for row in features],
        )
        dup_columns = list(duplicates[0].keys())
        conn.executemany(
            f"INSERT INTO synthetic_duplicates ({', '.join(dup_columns)}) VALUES ({', '.join('?' for _ in dup_columns)})",
            [tuple(row[col] for col in dup_columns) for row in duplicates],
        )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('fixture_version', ?)",
            (FIXTURE_VERSION,),
        )


_NUMERIC = {
    "amount",
    "log_amount",
    "amount_usd",
    "fraud_score",
    "local_hour",
    "local_dow",
    "is_night",
    "is_weekend",
    "is_cross_border",
    "customer_tenure_days",
    "product_tenure_days",
    "prior_tx_count",
    "prior_tx_count_1h",
    "prior_tx_count_24h",
    "prior_tx_count_7d",
    "secs_since_prev_tx",
    "prior_mean_amount_same_ccy",
    "amount_to_prior_mean",
    "prior_count_same_merchant",
    "prior_cross_border_count_30d",
}
