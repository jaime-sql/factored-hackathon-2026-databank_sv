# ruff: noqa: E501
"""Customer-scoped data access over gold. The ONLY entry point the app should use to read transactions."""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import CUSTOMER_KEY_RE, DB, SLICE

COLUMNS = [
    "transaction_key",
    "customer_key",
    "product_key",
    "product_type",
    "transaction_ts_utc",
    "transaction_ts_local",
    "transaction_type",
    "transaction_category",
    "amount",
    "currency",
    "channel",
    "merchant_name",
    "merchant_category",
    "transaction_country",
    "transaction_city",
    "transaction_status",
    "fraud_score",
]


class AccessError(ValueError):
    pass


def _validate(customer_key):
    if not isinstance(customer_key, str) or not CUSTOMER_KEY_RE.fullmatch(customer_key):
        raise AccessError("invalid customer_key")


def get_transactions(customer_key, backend="duckdb", path=None, limit=None):
    """Return the transactions of exactly one customer (list of dicts). Raises AccessError on a malformed key.
    A well-formed key that does not exist returns []. Rows are post-checked so another customer's row can never leak."""
    _validate(customer_key)
    sql = f"SELECT {', '.join(COLUMNS)} FROM {{t}} WHERE customer_key = ? ORDER BY transaction_ts_utc DESC"
    if limit is not None:
        if not isinstance(limit, int) or limit <= 0:
            raise AccessError("invalid limit")
        sql += f" LIMIT {int(limit)}"
    if backend == "duckdb":
        import duckdb

        con = duckdb.connect(path or DB, read_only=True)
        try:
            rows = con.execute(sql.format(t="gold.transactions_masked"), [customer_key]).fetchall()
        finally:
            con.close()
    elif backend == "sqlite":
        con = sqlite3.connect(f"file:{path or SLICE}?mode=ro", uri=True)
        try:
            rows = con.execute(sql.format(t="transactions"), [customer_key]).fetchall()
        finally:
            con.close()
    else:
        raise AccessError("unknown backend")
    out = [dict(zip(COLUMNS, r)) for r in rows]
    if any(r["customer_key"] != customer_key for r in out):  # defense in depth
        raise AccessError("isolation violation")
    return out
