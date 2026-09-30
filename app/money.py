"""Display helpers for amounts stored as integer cents. Nothing here moves money."""

from __future__ import annotations


def format_cents(cents: int, currency: str = "USD") -> str:
    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    rendered = f"{sign}${absolute // 100:,}.{absolute % 100:02d}"
    if currency != "USD":
        return f"{rendered} {currency}"
    return rendered
