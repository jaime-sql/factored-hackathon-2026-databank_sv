# ruff: noqa: E501
"""PII tests: gold tables, exported parquet, fixture and SQLite slice carry no direct identifiers or raw ids."""

import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import FIXTURES, OUT, SLICE, connect

PII_COLS = {
    "customer_id",
    "product_id",
    "transaction_id",
    "first_name",
    "last_name",
    "document_number",
    "document_type",
    "email",
    "mobile_phone",
    "landline_phone",
    "phone",
    "address",
    "postal_code",
    "date_of_birth",
    "ip_address",
    "latitude",
    "longitude",
    "product_number",
    "state",
    "city",
}
RAW_ID = re.compile(r"\b(CLI|PRD|TRX)-[A-Z0-9]{8,}")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}")
con = connect(read_only=True)
EMAILS = {
    r[0]
    for r in con.execute("SELECT email FROM silver.customers WHERE email IS NOT NULL").fetchall()
}
DOCS = {r[0] for r in con.execute("SELECT document_number FROM silver.customers").fetchall()}
PHONES = {
    r[0]
    for r in con.execute(
        "SELECT mobile_phone FROM silver.customers WHERE mobile_phone IS NOT NULL"
    ).fetchall()
}


def _scan_duck(rel):
    cols = [(r[0], r[1]) for r in con.execute(f"DESCRIBE SELECT * FROM {rel}").fetchall()]
    assert not ({c for c, _ in cols} & PII_COLS), {c for c, _ in cols} & PII_COLS
    for c, ty in cols:
        if ty != "VARCHAR":
            continue
        n = con.execute(f"""SELECT count(*) FROM {rel} WHERE regexp_matches("{c}", '(CLI|PRD|TRX)-[A-Z0-9]{{8,}}')
                            OR regexp_matches("{c}", '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[a-z]{{2,}}')
                            OR "{c}" IN (SELECT document_number FROM silver.customers)
                            OR "{c}" IN (SELECT mobile_phone FROM silver.customers WHERE mobile_phone IS NOT NULL)""").fetchone()[
            0
        ]
        assert n == 0, (rel, c, n)


def test_gold_tables():
    for t in ("gold.transactions_masked", "gold.customers_masked", "gold.fraud_features"):
        _scan_duck(t)


def test_exported_parquet_and_fixture():
    d = os.path.join(OUT, "gold")
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        _scan_duck(f"read_parquet('{os.path.join(d, f)}')")
    p = os.path.join(FIXTURES, "synthetic_duplicates.parquet")
    if os.path.exists(p):
        _scan_duck(f"read_parquet('{p}')")
        assert con.execute(f"SELECT bool_and(is_synthetic) FROM read_parquet('{p}')").fetchone()[0]


def test_sqlite_slice():
    if not os.path.exists(SLICE):
        return
    assert os.path.getsize(SLICE) < 50e6
    db = sqlite3.connect(SLICE)
    for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        cols = [r[1] for r in db.execute(f"PRAGMA table_info({t})")]
        assert not (set(cols) & PII_COLS), (t, set(cols) & PII_COLS)
        for row in db.execute(f"SELECT * FROM {t}"):
            for v in row:
                if isinstance(v, str):
                    assert (
                        not RAW_ID.search(v)
                        and not EMAIL.search(v)
                        and v not in DOCS
                        and v not in PHONES
                        and v not in EMAILS
                    ), (t, v[:40])
    assert (
        db.execute("SELECT count(*) FROM synthetic_duplicates WHERE is_synthetic != 1").fetchone()[
            0
        ]
        == 0
    )


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, str(e)[:300])
    sys.exit(1 if fails else 0)
