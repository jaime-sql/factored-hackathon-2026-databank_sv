"""Strict handoff packet. Eval labels and is_fraud are not fields."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TransactionFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_key: str
    product_key: str
    merchant_name: str
    merchant_category: str
    transaction_city: str
    transaction_country: str
    transaction_status: str
    amount: float
    currency: str
    transaction_ts_utc: str
    customer_tz: str
    transaction_ts_customer_local: str
    local_time_abbreviation: str


class TriageInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    band: Literal["high", "review", "low", "out_of_scope"]
    fraud_score: float | None
    model_risk_score: float | None
    model_version: str


class ActionTaken(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    verification_status: Literal["verified", "failed", "not_applicable"]


class HandoffPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    customer_key: str
    language: Literal["es", "pt", "other"]
    transaction: TransactionFacts
    verified_facts: list[str]
    triage: TriageInfo
    actions_taken: list[ActionTaken]
    open_questions: list[str] = Field(default_factory=list)
    recommended_next_step: str
    synthetic_duplicate: bool = False


def packet_is_complete(packet: HandoffPacket) -> bool:
    """A reviewer can act only when the charge identity, time, and next step are filled.

    merchant_name is required. Replies and packet_merchant fill it from category or type
    when the bank name is null, so a blank name is an incomplete packet.
    """
    transaction = packet.transaction
    required = (
        packet.case_id,
        packet.customer_key,
        packet.language,
        packet.recommended_next_step,
        packet.triage.band,
        packet.triage.model_version,
        transaction.transaction_key,
        transaction.merchant_name,
        transaction.transaction_status,
        transaction.currency,
        transaction.transaction_ts_utc,
        transaction.customer_tz,
        transaction.transaction_ts_customer_local,
    )
    if any(not str(value).strip() for value in required):
        return False
    return bool(packet.verified_facts)
