"""SQLite and Postgres reads. Every method is scoped to one customer_key."""

from __future__ import annotations

import sqlite3
from typing import Protocol

from app.bank.access import (
    CUSTOMER_COLUMNS,
    DUPLICATE_COLUMNS,
    TRANSACTION_COLUMNS,
    AccessError,
    assert_columns_safe,
    validate_customer_key,
)
from app.bank.fixture import feature_names
from app.bank.models import Customer, DuplicatePair, Transaction
from app.timeutil import as_utc

assert_columns_safe(TRANSACTION_COLUMNS)
assert_columns_safe(CUSTOMER_COLUMNS)
assert_columns_safe(DUPLICATE_COLUMNS)


class BankRepository(Protocol):
    def get_customer(self, customer_key: str) -> Customer | None: ...

    def get_transactions(self, customer_key: str, limit: int = 50) -> list[Transaction]: ...

    def get_transaction(self, customer_key: str, transaction_key: str) -> Transaction | None: ...

    def get_features(self, customer_key: str, transaction_key: str) -> dict[str, object] | None: ...

    def get_duplicate(self, customer_key: str, transaction_key: str) -> DuplicatePair | None: ...


def _limit(limit: int) -> int:
    if not isinstance(limit, int) or limit <= 0 or limit > 200:
        raise AccessError("invalid limit")
    return limit


class SQLBankRepository:
    def __init__(self, backend: str, path: str = "", dsn: str = "") -> None:
        if backend not in {"sqlite", "postgres"}:
            raise AccessError("unknown backend")
        self.backend = backend
        self.path = path
        self.dsn = dsn
        self._feature_names = feature_names()
        assert_columns_safe(tuple(self._feature_names))

    def _table(self, name: str) -> str:
        if self.backend == "postgres":
            return f"public.{name}"
        return name

    def _q(self, sql: str) -> str:
        if self.backend == "postgres":
            return sql.replace("?", "%s")
        return sql

    def _fetch(self, sql: str, params: tuple[object, ...]) -> list[dict[str, object]]:
        query = self._q(sql)
        if self.backend == "sqlite":
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        from app.db import connect_app

        with connect_app(self.dsn) as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_customer(self, customer_key: str) -> Customer | None:
        key = validate_customer_key(customer_key)
        columns = ", ".join(CUSTOMER_COLUMNS)
        rows = self._fetch(
            f"SELECT {columns} FROM {self._table('customers')} WHERE customer_key = ?",
            (key,),
        )
        if not rows:
            return None
        customer = Customer.from_row(rows[0])
        if customer.customer_key != key:
            raise AccessError("isolation violation")
        return customer

    def get_transactions(self, customer_key: str, limit: int = 50) -> list[Transaction]:
        key = validate_customer_key(customer_key)
        capped = _limit(limit)
        columns = ", ".join(TRANSACTION_COLUMNS)
        rows = self._fetch(
            f"SELECT {columns} FROM {self._table('transactions')} WHERE customer_key = ? "
            "ORDER BY transaction_ts_utc DESC LIMIT ?",
            (key, capped),
        )
        found = [Transaction.from_row(row) for row in rows]
        if any(tx.customer_key != key for tx in found):
            raise AccessError("isolation violation")
        if any("is_fraud" in row for row in rows):
            raise AccessError("isolation violation")
        return found

    def get_transaction(self, customer_key: str, transaction_key: str) -> Transaction | None:
        key = validate_customer_key(customer_key)
        columns = ", ".join(TRANSACTION_COLUMNS)
        rows = self._fetch(
            f"SELECT {columns} FROM {self._table('transactions')} "
            "WHERE customer_key = ? AND transaction_key = ?",
            (key, transaction_key),
        )
        if not rows:
            return None
        if "is_fraud" in rows[0]:
            raise AccessError("isolation violation")
        tx = Transaction.from_row(rows[0])
        if tx.customer_key != key:
            raise AccessError("isolation violation")
        return tx

    def get_features(self, customer_key: str, transaction_key: str) -> dict[str, object] | None:
        """Read model columns from fraud_features.

        The live table has no customer_key. Ownership is the join to transactions.
        Pending and Reversed charges have no feature row; the caller routes those
        by status and must not treat a missing row as LOW.
        """
        key = validate_customer_key(customer_key)
        features = self._table("fraud_features")
        transactions = self._table("transactions")
        columns = ", ".join(f"f.{name}" for name in self._feature_names)
        rows = self._fetch(
            f"SELECT {columns} FROM {features} AS f "
            f"INNER JOIN {transactions} AS t ON t.transaction_key = f.transaction_key "
            "WHERE t.customer_key = ? AND f.transaction_key = ?",
            (key, transaction_key),
        )
        if not rows:
            return None
        row = rows[0]
        if "is_fraud" in row or "customer_key" in row:
            raise AccessError("isolation violation")
        return row

    def get_duplicate(self, customer_key: str, transaction_key: str) -> DuplicatePair | None:
        key = validate_customer_key(customer_key)
        columns = ", ".join(DUPLICATE_COLUMNS)
        rows = self._fetch(
            f"SELECT {columns} FROM {self._table('synthetic_duplicates')} "
            "WHERE customer_key = ? AND transaction_key = ? AND is_synthetic = 1",
            (key, transaction_key),
        )
        if not rows:
            return None
        row = rows[0]
        if str(row["customer_key"]) != key or int(str(row["is_synthetic"])) != 1:
            raise AccessError("isolation violation")
        source = str(row["source_transaction_key"])
        current = str(row["transaction_key"])
        other_key = source if current != source else ""
        if not other_key:
            siblings = self._fetch(
                "SELECT transaction_key, transaction_ts_utc FROM "
                f"{self._table('synthetic_duplicates')} "
                "WHERE customer_key = ? AND source_transaction_key = ? AND transaction_key <> ? "
                "AND is_synthetic = 1",
                (key, source, current),
            )
            other_key = str(siblings[0]["transaction_key"]) if siblings else ""
            other_ts = as_utc(siblings[0]["transaction_ts_utc"]) if siblings else None
        else:
            other_rows = self._fetch(
                "SELECT transaction_ts_utc FROM "
                f"{self._table('synthetic_duplicates')} "
                "WHERE customer_key = ? AND transaction_key = ? AND is_synthetic = 1",
                (key, other_key),
            )
            other_ts = as_utc(other_rows[0]["transaction_ts_utc"]) if other_rows else None
        return DuplicatePair(
            case_id=str(row["case_id"]),
            role=str(row["role"]),
            is_synthetic=1,
            source_transaction_key=source,
            transaction_key=current,
            customer_key=key,
            merchant_name=str(row["merchant_name"]),
            amount=float(str(row["amount"])),
            currency=str(row["currency"]),
            other_transaction_key=other_key,
            other_ts_utc=other_ts,
        )
