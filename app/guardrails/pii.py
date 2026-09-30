"""Mask direct identifiers before text is logged or sent to a model.

Name coverage is a dictionary of known synthetic customers plus a "my name is"
pattern. It is not a general NER model. That replacement is a machine-learning seam.
"""

from __future__ import annotations

import re

_NAMES: list[str] = []

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\b\d{3})[\s.-]\d{3}[\s.-]\d{4}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_LABELED_ID = re.compile(
    r"(?i)\b(?:ssn|social security|national\s*id|nin|id\s*number)\b[:\s#-]*[A-Z0-9-]{4,}"
)
_ACCOUNT = re.compile(r"(?i)\b(?:account|acct)(?:\s+(?:number|no\.?|#))?[\s:#-]*\d{6,17}\b")
_CARD = re.compile(r"\b(?:\d{4}[ -]){3}\d{4}\b|\b\d{13,19}\b")
_NAME_INTRO = re.compile(r"(?i)\bmy name is\s+[a-z][a-z'’.-]+(?:\s+[a-z][a-z'’.-]+){0,2}")

_SENSITIVE_KEYS = {
    "email",
    "phone",
    "national_id",
    "full_name",
    "display_name",
    "name",
    "account_number",
    "pan",
    "card_number",
    "ssn",
    "password",
    "token",
    "customer_id",
    "session_id",
}


def set_known_names(names: list[str]) -> None:
    """Replace the process-wide name dictionary used by logs and the redactor."""
    global _NAMES
    cleaned = {name.strip() for name in names if len(name.strip()) >= 3}
    _NAMES = sorted(cleaned, key=len, reverse=True)


def known_names() -> list[str]:
    return list(_NAMES)


def luhn_ok(number: str) -> bool:
    digits = [int(char) for char in number if char.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    alt = False
    for digit in reversed(digits):
        if alt:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
        alt = not alt
    return total % 10 == 0


def _mask_cards(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        grouped = bool(re.search(r"\d{4}[ -]\d{4}", raw))
        if 13 <= len(digits) <= 19 and (luhn_ok(digits) or grouped):
            return "[CARD]"
        return raw

    return _CARD.sub(replace, text)


def redact(text: str, extra_names: list[str] | None = None) -> str:
    """Replace direct identifiers with stable tokens. Safe to run more than once."""
    if not text:
        return text
    names = list(_NAMES)
    if extra_names:
        names.extend(name.strip() for name in extra_names if name and len(name.strip()) >= 3)
        names = sorted(set(names), key=len, reverse=True)
    masked = _EMAIL.sub("[EMAIL]", text)
    masked = _LABELED_ID.sub("[NATIONAL_ID]", masked)
    masked = _SSN.sub("[NATIONAL_ID]", masked)
    masked = _PHONE.sub("[PHONE]", masked)
    masked = _mask_cards(masked)
    masked = _ACCOUNT.sub("[ACCOUNT]", masked)
    for name in names:
        masked = re.sub(re.escape(name), "[NAME]", masked, flags=re.IGNORECASE)
    masked = _NAME_INTRO.sub("my name is [NAME]", masked)
    return masked


def mask_payload(value: object) -> object:
    """Recursively redact strings and drop sensitive keys from tool arguments and results."""
    if isinstance(value, dict):
        masked: dict[str, object] = {}
        for key, item in value.items():
            if key.lower() in _SENSITIVE_KEYS:
                masked[key] = (
                    "[ID]" if key.lower() in {"customer_id", "session_id"} else "[REDACTED]"
                )
            else:
                masked[key] = mask_payload(item)
        return masked
    if isinstance(value, list):
        return [mask_payload(item) for item in value]
    if isinstance(value, tuple):
        return [mask_payload(item) for item in value]
    if isinstance(value, str):
        return redact(value)
    return value
