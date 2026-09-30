"""Opaque ids. Case ids are server-generated text UUIDs, not proof that money moved."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime


def new_case_id() -> str:
    """Eval joins app.audit_current on this value. Clients cannot choose it."""
    return str(uuid.uuid4())


def new_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return f"{prefix}-{stamp}-{secrets.token_hex(3).upper()}"
