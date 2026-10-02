"""Customer-language reply draft from handoff packet facts only.

Template mode is the default and the fallback when a model call fails.
The draft is never sent. The agent edits and sends it.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.handoff.packet import HandoffPacket
from app.i18n import (
    display_next_step,
    localize_stored_merchant,
    mask_merchant,
    money,
    transaction_status_label,
)
from app.timeutil import present_time

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DraftResult:
    text: str
    facts: dict[str, str]
    used_model: bool
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    status: str


def compose_draft(packet: HandoffPacket, country: str, settings: Settings) -> DraftResult:
    facts = fact_sheet(packet, country)
    template = _template(facts)
    provider = settings.resolved_llm_provider()
    if provider == "template":
        return DraftResult(template, facts, False, "", 0, 0, 0, "template")
    try:
        text, model, latency_ms, input_tokens, output_tokens = _complete(settings, provider, facts)
    except Exception as exc:
        logger.warning("reply draft fell back to template (%s)", type(exc).__name__)
        return DraftResult(template, facts, True, _model_name(settings, provider), 0, 0, 0, "error")
    cleaned = (text or "").strip()
    if not cleaned:
        return DraftResult(
            template, facts, True, _model_name(settings, provider), latency_ms, 0, 0, "error"
        )
    return DraftResult(cleaned, facts, True, model, latency_ms, input_tokens, output_tokens, "ok")


def fact_sheet(packet: HandoffPacket, country: str) -> dict[str, str]:
    language = packet.language if packet.language in {"es", "pt"} else "es"
    transaction = packet.transaction
    try:
        date = present_time(
            transaction.transaction_ts_utc,
            transaction.customer_tz or None,
            transaction.transaction_country or None,
            language,
        )["label"]
    except (TypeError, ValueError):
        date = transaction.transaction_ts_customer_local
    merchant = mask_merchant(localize_stored_merchant(language, transaction.merchant_name or ""))
    blocked = any(
        item.name == "block_card" and item.verification_status == "verified"
        for item in packet.actions_taken
    )
    reason = "fraud_rule" if blocked else "fraud_model"
    return {
        "language": language,
        "amount": money(transaction.amount, transaction.currency, country),
        "date": date,
        "merchant": merchant,
        "status": transaction_status_label(language, transaction.transaction_status),
        "action": _action_sentence(language, blocked),
        "next_step": display_next_step(
            language, reason, card_blocked=blocked, stored=packet.recommended_next_step
        ),
    }


def _template(facts: dict[str, str]) -> str:
    if facts["language"] == "pt":
        return (
            f"Olá. Vimos a cobrança de {facts['amount']} em {facts['date']} "
            f"em {facts['merchant']}. O estado é {facts['status']}. "
            f"{facts['action']} {facts['next_step']}"
        )
    return (
        f"Hola. Vimos el cargo de {facts['amount']} del {facts['date']} "
        f"en {facts['merchant']}. El estado es {facts['status']}. "
        f"{facts['action']} {facts['next_step']}"
    )


def _action_sentence(language: str, blocked: bool) -> str:
    if language == "pt":
        if blocked:
            return "O cartão foi bloqueado."
        return "O caso foi para uma pessoa."
    if blocked:
        return "La tarjeta quedó bloqueada."
    return "El caso pasó a una persona."


def _model_name(settings: Settings, provider: str) -> str:
    if provider == "openrouter":
        return settings.openrouter_model
    return settings.openai_model


def _complete(
    settings: Settings, provider: str, facts: dict[str, str]
) -> tuple[str, str, int, int, int]:
    import time

    model = _model_name(settings, provider)
    if provider == "openrouter":
        url = settings.openrouter_base_url.rstrip("/") + "/chat/completions"
        key = settings.openrouter_api_key
    else:
        base = settings.openai_base_url.strip() or "https://api.openai.com/v1"
        url = base.rstrip("/") + "/chat/completions"
        key = settings.openai_api_key
    if not key.strip():
        raise RuntimeError("missing api key")
    language = "português" if facts["language"] == "pt" else "español"
    prompt = (
        "Write one short reply to the customer in "
        f"{language}. Use only these facts. Do not add an amount, date, or merchant "
        "that is not listed.\n"
        f"amount: {facts['amount']}\n"
        f"date: {facts['date']}\n"
        f"merchant: {facts['merchant']}\n"
        f"status: {facts['status']}\n"
        f"action: {facts['action']}\n"
        f"next step: {facts['next_step']}"
    )
    body = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": "You draft a bank reply from the facts you are given.",
                },
                {"role": "user", "content": prompt},
            ],
        }
    ).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=settings.llm_timeout_seconds) as response:
            payload: dict[str, Any] = json.loads(response.read().decode())
    except urllib.error.URLError as exc:
        raise RuntimeError("llm request failed") from exc
    latency_ms = int((time.perf_counter() - started) * 1000)
    raw_usage = payload.get("usage")
    usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("llm response had no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else ""
    if not isinstance(content, str):
        content = ""
    return (
        content.strip(),
        model,
        latency_ms,
        int(usage.get("prompt_tokens") or 0),
        int(usage.get("completion_tokens") or 0),
    )
