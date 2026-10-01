"""Customer-local time from transaction_ts_utc and customers.tz.

Display never reads transaction_ts_local. A missing tz falls back from country
only for older SQLite slices. Mexico is not assumed to be Mexico City when tz is set.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.i18n import months

COUNTRY_TZ_FALLBACK = {
    "AR": "America/Argentina/Buenos_Aires",
    "CO": "America/Bogota",
    "MX": "America/Mexico_City",
    "ARGENTINA": "America/Argentina/Buenos_Aires",
    "COLOMBIA": "America/Bogota",
    "MEXICO": "America/Mexico_City",
}


def as_utc(value: object) -> datetime:
    """Normalize Postgres timestamptz and SQLite ISO text to an aware UTC datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    raise TypeError(f"unsupported timestamp: {type(value).__name__}")


def resolve_tz(tz: str | None, country: str | None) -> str:
    """Use customers.tz when it is present. Country fallback is only for a missing tz."""
    if tz and tz.strip():
        return tz.strip()
    return COUNTRY_TZ_FALLBACK.get((country or "").strip().upper(), "UTC")


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def abbreviation(local: datetime) -> str:
    """Letter abbreviations from tzdata, or an explicit UTC offset when tzdata has no letters."""
    name = local.tzname() or ""
    if name and not name.startswith(("+", "-")) and not name.replace(":", "").isdigit():
        return name
    offset = local.utcoffset()
    if offset is None:
        return "UTC"
    hours = int(offset.total_seconds() // 3600)
    sign = "+" if hours >= 0 else "-"
    return f"UTC{sign}{abs(hours)}"


def present_time(
    utc_value: object, tz: str | None, country: str | None, language: str
) -> dict[str, str]:
    utc = as_utc(utc_value)
    zone_name = resolve_tz(tz, country)
    local = utc.astimezone(_zone(zone_name))
    abbrev = abbreviation(local)
    names = months(language)
    label = f"{local.day} {names[local.month - 1]} {local.year}, {local.strftime('%H:%M')} {abbrev}"
    return {
        "utc": utc.isoformat(),
        "tz": zone_name,
        "local_iso": local.isoformat(),
        "abbreviation": abbrev,
        "label": label,
    }
