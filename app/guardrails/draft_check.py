"""Deterministic check that a reply draft only uses packet facts.

grounded(draft, packet) returns {"ok": bool, "unsupported_facts": list[str]}.
Every amount, date, and merchant token in the draft must appear in the packet.
"""

from __future__ import annotations

import re
from typing import Any

_AMOUNT = re.compile(
    r"(?:US\$|R\$|S/|\$)\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})"
    r"|\b(?:USD|MXN|COP|ARS|BRL|EUR)\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})"
    r"|\b\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})\b"
)
_DATE = re.compile(
    r"\b\d{1,2}\s+[A-Za-zÁÉÍÓÚáéíóúñÑ]{3,}\.?\s+\d{4}\b|\b\d{4}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)
_MERCHANT = re.compile(r"\S*[•*]{2,}\S*")


def grounded(draft: str, packet: dict[str, Any]) -> dict[str, Any]:
    text = draft or ""
    amounts = _strings(packet, "amount", "amounts")
    dates = _strings(packet, "date", "dates", "local_time")
    merchants = _strings(packet, "merchant", "merchants")
    unsupported: list[str] = []
    for found in _AMOUNT.findall(text):
        if not _amount_allowed(found, amounts):
            unsupported.append(found.strip())
    for found in _DATE.findall(text):
        if not _date_allowed(found, dates):
            unsupported.append(found.strip())
    for found in _MERCHANT.findall(text):
        token = found.strip().strip(".,;:!?")
        if token and not _merchant_allowed(token, merchants):
            unsupported.append(token)
    unique = list(dict.fromkeys(unsupported))
    return {"ok": not unique, "unsupported_facts": unique}


def _strings(packet: dict[str, Any], *keys: str) -> list[str]:
    found: list[str] = []
    for key in keys:
        value = packet.get(key)
        if isinstance(value, str) and value.strip():
            found.append(value.strip())
        elif isinstance(value, list):
            found.extend(str(item).strip() for item in value if str(item).strip())
    return found


def _amount_allowed(found: str, allowed: list[str]) -> bool:
    key = _amount_key(found)
    if key is None:
        return False
    return any(_amount_key(item) == key for item in allowed)


def _amount_key(text: str) -> str | None:
    cleaned = re.sub(
        r"^(?:US\$|R\$|S/|\$|USD|MXN|COP|ARS|BRL|EUR)\s*",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    )
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        tail = cleaned.rsplit(",", 1)[-1]
        cleaned = (
            cleaned.replace(".", "").replace(",", ".")
            if len(tail) == 2
            else cleaned.replace(",", "")
        )
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")
    elif "." in cleaned:
        tail = cleaned.rsplit(".", 1)[-1]
        if len(tail) != 2:
            cleaned = cleaned.replace(".", "")
    try:
        return f"{float(cleaned):.2f}"
    except ValueError:
        return None


def _date_allowed(found: str, allowed: list[str]) -> bool:
    needle = " ".join(found.casefold().split())
    for item in allowed:
        haystack = " ".join(item.casefold().split())
        if needle in haystack or haystack in needle:
            return True
    return False


def _merchant_allowed(found: str, allowed: list[str]) -> bool:
    token = " ".join(found.casefold().split())
    if not token:
        return False
    for item in allowed:
        haystack = " ".join(item.casefold().split())
        if token in haystack.split() or token in haystack:
            return True
    return False
