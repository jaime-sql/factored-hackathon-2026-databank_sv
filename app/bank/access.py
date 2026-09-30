"""The only column lists the app may read from the bank slice.

`is_fraud` is an offline answer key. It may exist on the SQLite fixture as a trap.
It is not selected here. `transaction_ts_local` is not selected; display uses
transaction_ts_utc plus customers.tz.
"""

from __future__ import annotations

import re

CUSTOMER_KEY_RE = re.compile(r"^[A-Za-z0-9:_-]{4,80}$")

CUSTOMER_COLUMNS: tuple[str, ...] = (
    "customer_key",
    "customer_country",
    "customer_segment",
    "customer_accent",
    "tz",
)

TRANSACTION_COLUMNS: tuple[str, ...] = (
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
    "customer_country",
    "customer_segment",
    "customer_accent",
    "transaction_ts_utc",
    "process_date",
    "amount",
    "amount_usd",
    "fraud_score",
)

DUPLICATE_COLUMNS: tuple[str, ...] = (
    "case_id",
    "scenario",
    "role",
    "is_synthetic",
    "seconds_after_original",
    "source_transaction_key",
    "transaction_key",
    "customer_key",
    "merchant_name",
    "amount",
    "currency",
    "transaction_status",
    "transaction_ts_utc",
    "transaction_city",
)

FORBIDDEN_READ_COLUMNS = frozenset({"is_fraud", "transaction_ts_local"})


class AccessError(ValueError):
    pass


def validate_customer_key(customer_key: object) -> str:
    if not isinstance(customer_key, str) or not CUSTOMER_KEY_RE.fullmatch(customer_key):
        raise AccessError("invalid customer_key")
    return customer_key


def assert_columns_safe(columns: tuple[str, ...]) -> None:
    leaked = FORBIDDEN_READ_COLUMNS.intersection(columns)
    if leaked:
        raise AccessError(f"forbidden columns in read list: {sorted(leaked)}")
