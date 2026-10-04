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
    strong: bool = False


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
        strong = False
        if merchant:
            name = fold(tx.merchant_name)
            query = fold(merchant)
            if name and (query == name or query in name or _tokens(query) & _tokens(name)):
                score += 6
                hits += 1
                strong = True
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
                strong = True
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
            matches.append(Match(tx, score, hits, strong))
    if not matches:
        return [], False
    matches.sort(key=lambda m: (-m.score, -m.tx.transaction_ts_utc.timestamp()))
    top = matches[0]
    runner_up = matches[1].score if len(matches) > 1 else 0
    # An exact amount or merchant name that clearly beats the next charge is enough
    # even when another clue (often a guessed year) does not line up.
    clear_lead = top.strong and top.score - runner_up >= 4
    confident = top.score > runner_up and (top.hits >= clues or clear_lead)
    if confident:
        return [top.tx], True
    return [m.tx for m in matches[:limit]], False


# Status questions -------------------------------------------------------------------------

_PENDING_WORDS = ("pendiente", "pendientes", "pendente", "pendentes", "retenido", "procesando")
_REVERSED_WORDS = ("revert", "reversad", "reversa", "devuelt", "devolvi", "estorn", "regres")
_STATUS_PHRASES = (
    "estado",
    "status",
    "que paso",
    "que pasa",
    "o que aconteceu",
    "por que aparece",
    "por que sigue",
    "todavia",
    "aun no",
    "ainda",
    "no se ha cobrado",
    "nao foi cobrad",
    "sigue apareciendo",
    "en proceso",
    "se cobro o no",
    "ya se cobro",
)
_DISPUTE_PHRASES = (
    "no reconozco",
    "no lo reconozco",
    "nao reconheco",
    "fraude",
    "no hice",
    "no fui yo",
    "nao fui eu",
    "robo",
    "robaron",
    "clonad",
)
_MONTHS = {
    "ene": 1, "enero": 1, "jan": 1, "janeiro": 1,
    "feb": 2, "febrero": 2, "fev": 2, "fevereiro": 2,
    "mar": 3, "marzo": 3, "marco": 3,
    "abr": 4, "abril": 4,
    "may": 5, "mayo": 5, "mai": 5, "maio": 5,
    "jun": 6, "junio": 6, "junho": 6,
    "jul": 7, "julio": 7, "julho": 7,
    "ago": 8, "agosto": 8,
    "sep": 9, "sept": 9, "septiembre": 9, "set": 9, "setembro": 9,
    "oct": 10, "octubre": 10, "out": 10, "outubro": 10,
    "nov": 11, "noviembre": 11, "novembro": 11,
    "dic": 12, "diciembre": 12, "dez": 12, "dezembro": 12,
}  # fmt: skip
_STOP = set(
    "que por para con del los las una uno este esta ese esa cargo cargos cobro cobros "
    "pago aparece sigue tengo tiene mis mio cobranca cobrancas minha meu sobre como "
    "cuando donde porque aun todavia ainda estado status".split()
)


def _status_words(message: str) -> str:
    text = fold(message)
    if any(word in text for word in _REVERSED_WORDS):
        return "Reversed"
    if any(word in text.split() for word in _PENDING_WORDS):
        return "Pending"
    return ""


def is_status_question(message: str) -> bool:
    """The customer asks where a charge stands (pending, reversed, what happened)."""
    text = f" {fold(message)} "
    if _status_words(message):
        return True
    if any(f" {phrase}" in text for phrase in _DISPUTE_PHRASES):
        return False
    return any(f" {phrase} " in text or f" {phrase}" in text for phrase in _STATUS_PHRASES)


def _message_amounts(message: str) -> list[float]:
    found = []
    for raw in re.findall(r"\d[\d.,]*", message or ""):
        clean = raw.rstrip(".,")
        if re.search(r",\d{1,2}$", clean):
            clean = clean.replace(".", "").replace(",", ".")
        else:
            clean = clean.replace(",", "")
        try:
            value = float(clean)
        except ValueError:
            continue
        if value > 0:
            found.append(value)
    return found


def _fits(
    tx: Transaction, customer: Customer, args: dict[str, Any], message: str
) -> tuple[int, int]:
    """(clues given, fit score) from the model's arguments and the message.

    A merchant name or an exact amount weighs 3; a category, type or month weighs 1.
    """
    words = _tokens(message) - _STOP
    clues = 0
    hits = 0
    merchant_words = _tokens(args.get("comercio")) | words
    name = _tokens(tx.merchant_name)
    category_words = set(_CATEGORY_WORDS.get(tx.merchant_category or "", "").split())
    type_words = set(_TYPE_WORDS.get(tx.transaction_type or "", "").split())
    all_category_words = {w for v in _CATEGORY_WORDS.values() for w in v.split()}
    all_type_words = {w for v in _TYPE_WORDS.values() for w in v.split()}
    named = merchant_words & (all_category_words | all_type_words)
    if args.get("comercio") or named:
        clues += 1
        if name & merchant_words:
            hits += 3
        elif category_words & merchant_words or type_words & merchant_words:
            hits += 1
    if args.get("categoria"):
        clues += 1
        if _category_for(str(args["categoria"])) == tx.merchant_category:
            hits += 1
    amounts = _message_amounts(message)
    try:
        if args.get("monto") not in (None, ""):
            amounts.append(float(args["monto"]))
    except (TypeError, ValueError):
        pass
    amounts = [a for a in amounts if not (1900 <= a <= 2100 and float(a).is_integer())]
    if amounts:
        clues += 1
        if any(abs(float(tx.amount) - a) <= max(0.51, a * 0.01) for a in amounts):
            hits += 3
    local = describe(tx, customer, "es")["fecha"]
    year, month, _day = (int(part) for part in local.split("-"))
    months_said = {_MONTHS[w] for w in fold(message).split() if w in _MONTHS}
    wanted = _parse_date(args.get("fecha"))
    if wanted is not None:
        months_said.add(wanted.month)
    if months_said:
        clues += 1
        if month in months_said:
            hits += 1
    return clues, hits


def status_pick(
    transactions: list[Transaction],
    customer: Customer,
    args: dict[str, Any],
    message: str,
    *,
    limit: int = 3,
) -> tuple[list[Transaction], bool] | None:
    """Pending and reversed charges first for a status question.

    Returns (charges, confident), or None when no pending/reversed charge fits, so the
    normal search runs. Confident when exactly one pending/reversed charge plausibly fits.
    """
    pool = [tx for tx in transactions if tx.transaction_status in {"Pending", "Reversed"}]
    asked = _status_words(message)
    given = str(args.get("estado") or "").strip().capitalize()
    asked = asked or (given if given in {"Pending", "Reversed"} else "")
    if asked and any(tx.transaction_status == asked for tx in pool):
        pool = [tx for tx in pool if tx.transaction_status == asked]
    if not pool:
        return None
    pool.sort(key=lambda tx: tx.transaction_ts_utc, reverse=True)
    scored = [(tx, *_fits(tx, customer, args, message)) for tx in pool]
    clues = max(item[1] for item in scored)
    if clues == 0:
        if len(pool) == 1:
            return [pool[0]], True
        return pool[:limit], False
    best = max(item[2] for item in scored)
    if best == 0:
        # The words point somewhere else (maybe an approved charge): use the normal search.
        return None
    top = [item[0] for item in scored if item[2] == best]
    if len(top) == 1:
        return top, True
    return top[:limit], False
