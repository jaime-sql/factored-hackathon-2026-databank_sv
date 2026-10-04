"""Charge search and descriptions for the agent tools. Reads only; scoring stays in the engine."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.bank.models import Customer, Transaction
from app.i18n import merchant_label, money, months, transaction_status_label
from app.timeutil import present_time

CATEGORIES = ("Transport", "Food", "Health", "Entertainment", "Services", "Other")
TYPES = ("Purchase", "Transfer", "Withdrawal", "Deposit", "Payment", "Adjustment")
STATUSES = ("Pending", "Reversed", "Approved", "Declined")

# Words a customer uses for a category or a transaction type, accent-free.
_CATEGORY_WORDS = {
    "Transport": (
        "transporte uber taxi didi cabify gasolina gasolinera combustible estacion "
        "servicio viaje transport onibus posto"
    ),
    "Food": "comida restaurante super supermercado mercado tienda alimentacao food almuerzo cena",
    "Health": "salud farmacia clinica medico laboratorio hospital saude health",
    "Entertainment": (
        "entretenimiento cine streaming concierto musica teatro netflix spotify "
        "entretenimento entertainment"
    ),
    "Services": "servicios telefono internet cable luz agua telefonica servicos services",
    "Other": "boutique moda ropa centro comercial ferreteria otros outros",
}
_TYPE_WORDS = {
    "Transfer": "transferencia transfer",
    "Withdrawal": "retiro cajero saque withdrawal",
    "Deposit": "deposito deposit",
    "Payment": "pago pagamento payment",
    "Purchase": "compra purchase",
    "Adjustment": "ajuste adjustment",
}


def fold(text: object) -> str:
    raw = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", raw.lower()).strip()


def _tokens(text: object) -> set[str]:
    return {token for token in fold(text).split() if len(token) >= 3}


@dataclass
class Match:
    tx: Transaction
    score: int
    hits: int


def describe(tx: Transaction, customer: Customer, language: str) -> dict[str, Any]:
    """Charge facts shown to the model and the customer. No customer identity."""
    shown = present_time(tx.transaction_ts_utc, customer.tz, customer.customer_country, language)
    local = shown["local_iso"][:10]
    year, month, day = (int(part) for part in local.split("-"))
    home = tx.customer_country or customer.customer_country
    return {
        "transaction_key": tx.transaction_key,
        "comercio": merchant_label(
            language, tx.merchant_name, tx.merchant_category, tx.transaction_type
        ),
        "tiene_nombre_de_comercio": bool((tx.merchant_name or "").strip()),
        "categoria": tx.merchant_category or "",
        "tipo": tx.transaction_type or "",
        "monto": money(tx.amount, tx.currency, home),
        "monto_numero": round(float(tx.amount), 2),
        "fecha": local,
        "fecha_corta": f"{day} {months(language)[month - 1]} {year}",
        "hora_local": shown["label"],
        "estado": tx.transaction_status,
        "estado_texto": transaction_status_label(language, tx.transaction_status),
    }


def _category_for(word: str) -> str | None:
    key = fold(word)
    if not key:
        return None
    for name in CATEGORIES:
        if fold(name) == key:
            return name
    for name, words in _CATEGORY_WORDS.items():
        if key in words.split() or any(token in words.split() for token in key.split()):
            return name
    return None


def _type_for(word: str) -> str | None:
    key = fold(word)
    if not key:
        return None
    for name in TYPES:
        if fold(name) == key:
            return name
    for name, words in _TYPE_WORDS.items():
        if any(token in words.split() for token in key.split()):
            return name
    return None


def _parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    found = re.match(r"(\d{4})-(\d{1,2})(?:-(\d{1,2}))?", text)
    if not found:
        return None
    try:
        return date(int(found[1]), int(found[2]), int(found[3] or 1))
    except ValueError:
        return None


def search(
    transactions: list[Transaction],
    customer: Customer,
    args: dict[str, Any],
    *,
    limit: int = 3,
) -> tuple[list[Transaction], bool]:
    """Rank charges by merchant, category, type, amount, date, and status.

    Returns (charges, confident). Confident means one charge clearly fits every clue
    given. Otherwise up to ``limit`` candidates come back and the customer chooses.
    """
    merchant = str(args.get("comercio") or "").strip()
    category = _category_for(str(args.get("categoria") or "")) if args.get("categoria") else None
    kind = _type_for(str(args.get("tipo") or "")) if args.get("tipo") else None
    status = str(args.get("estado") or "").strip().capitalize()
    status = status if status in STATUSES else ""
    amount: float | None
    try:
        amount = float(args["monto"]) if args.get("monto") not in (None, "") else None
    except (TypeError, ValueError):
        amount = None
    wanted = _parse_date(args.get("fecha"))
    day_given = bool(re.match(r"\d{4}-\d{1,2}-\d{1,2}", str(args.get("fecha") or "")))
    merchant_category = _category_for(merchant) if merchant else None
    merchant_kind = _type_for(merchant) if merchant else None
    clues = sum(
        1 for value in (merchant, category, kind, status, amount, wanted) if value not in ("", None)
    )
    ordered = sorted(transactions, key=lambda tx: tx.transaction_ts_utc, reverse=True)
    if clues == 0:
        recent = [tx for tx in ordered if tx.transaction_type == "Purchase"] or ordered
        return recent[:limit], False
    matches: list[Match] = []
    for tx in ordered:
        score = 0
        hits = 0
        if merchant:
            name = fold(tx.merchant_name)
            query = fold(merchant)
            if name and (query == name or query in name or _tokens(query) & _tokens(name)):
                score += 6
                hits += 1
            elif merchant_category and tx.merchant_category == merchant_category:
                score += 2
            elif merchant_kind and tx.transaction_type == merchant_kind:
                score += 2
        if category and tx.merchant_category == category:
            score += 3
            hits += 1
        if kind and tx.transaction_type == kind:
            score += 3
            hits += 1
        if status and tx.transaction_status == status:
            score += 4
            hits += 1
        if amount is not None:
            gap = abs(float(tx.amount) - amount)
            if gap <= max(0.51, abs(amount) * 0.005):
                score += 6
                hits += 1
            elif gap <= abs(amount) * 0.1:
                score += 1
        if wanted is not None:
            local = describe(tx, customer, "es")["fecha"]
            year, month, day = (int(part) for part in local.split("-"))
            if day_given and (year, month, day) == (wanted.year, wanted.month, wanted.day):
                score += 4
                hits += 1
            elif (year, month) == (wanted.year, wanted.month):
                score += 2 if not day_given else 1
                hits += 0 if day_given else 1
        if score > 0:
            matches.append(Match(tx, score, hits))
    if not matches:
        return [], False
    matches.sort(key=lambda m: (-m.score, -m.tx.transaction_ts_utc.timestamp()))
    top = matches[0]
    runner_up = matches[1].score if len(matches) > 1 else 0
    confident = top.hits >= clues and top.score > runner_up
    if confident:
        return [top.tx], True
    return [m.tx for m in matches[:limit]], False
