"""Rows the agent is allowed to see. There is no is_fraud field."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


@dataclass(frozen=True)
class Customer:
    customer_key: str
    customer_country: str
    customer_segment: str
    customer_accent: str | None
    tz: str | None

    @classmethod
    def from_row(cls, row: dict[str, object]) -> Customer:
        accent = row.get("customer_accent")
        tz = row.get("tz")
        return cls(
            customer_key=str(row["customer_key"]),
            customer_country=str(row["customer_country"]),
            customer_segment=str(row["customer_segment"]),
            customer_accent=None if accent in (None, "") else str(accent),
            tz=None if tz in (None, "") else str(tz),
        )


@dataclass(frozen=True)
class Transaction:
    transaction_key: str
    customer_key: str
    product_key: str
    product_type: str
    transaction_type: str
    transaction_category: str
    currency: str
    channel: str
    branch_id: str
    merchant_name: str
    merchant_category: str
    transaction_country: str
    transaction_city: str
    transaction_status: str
    response_code: str
    customer_country: str
    customer_segment: str
    customer_accent: str | None
    transaction_ts_utc: datetime
    process_date: str
    amount: float
    amount_usd: float
    fraud_score: float | None

    @classmethod
    def from_row(cls, row: dict[str, object]) -> Transaction:
        from app.timeutil import as_utc

        accent = row.get("customer_accent")
        return cls(
            transaction_key=str(row["transaction_key"]),
            customer_key=str(row["customer_key"]),
            product_key=str(row.get("product_key") or ""),
            product_type=str(row.get("product_type") or ""),
            transaction_type=str(row.get("transaction_type") or ""),
            transaction_category=str(row.get("transaction_category") or ""),
            currency=str(row.get("currency") or ""),
            channel=str(row.get("channel") or ""),
            branch_id=str(row.get("branch_id") or ""),
            merchant_name=str(row.get("merchant_name") or ""),
            merchant_category=str(row.get("merchant_category") or ""),
            transaction_country=str(row.get("transaction_country") or ""),
            transaction_city=str(row.get("transaction_city") or ""),
            transaction_status=str(row.get("transaction_status") or ""),
            response_code=str(row.get("response_code") or ""),
            customer_country=str(row.get("customer_country") or ""),
            customer_segment=str(row.get("customer_segment") or ""),
            customer_accent=None if accent in (None, "") else str(accent),
            transaction_ts_utc=as_utc(row["transaction_ts_utc"]),
            process_date=str(row.get("process_date") or ""),
            amount=float(str(row.get("amount") or 0)),
            amount_usd=float(str(row.get("amount_usd") or 0)),
            fraud_score=_float_or_none(row.get("fraud_score")),
        )


@dataclass(frozen=True)
class DuplicatePair:
    case_id: str
    role: str
    is_synthetic: int
    source_transaction_key: str
    transaction_key: str
    customer_key: str
    merchant_name: str
    amount: float
    currency: str
    other_transaction_key: str
    other_ts_utc: datetime | None
