"""Customer session cookies and the local agent token.

The eval runner uses a separate header, checked in eval_access.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from app.config import Settings


def sign_customer(secret: str, customer_key: str, ttl_hours: int) -> str:
    exp = int(time.time()) + ttl_hours * 3600
    body = f"{customer_key}.{exp}"
    digest = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"cust.{body}.{digest}"


def read_customer(secret: str, token: str) -> str | None:
    parts = token.split(".")
    if len(parts) != 4 or parts[0] != "cust":
        return None
    customer_key, exp, digest = parts[1], parts[2], parts[3]
    body = f"{customer_key}.{exp}"
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, expected):
        return None
    try:
        expires = int(exp)
    except ValueError:
        return None
    if expires < int(time.time()):
        return None
    return customer_key


def _same_token(presented: str, expected: str) -> bool:
    if not presented or not expected or len(presented) != len(expected):
        return False
    return hmac.compare_digest(presented, expected)


def agent_role(settings: Settings, token: str) -> str | None:
    """admin for DEMO_AGENT_TOKEN, judge for DEMO_JUDGE_TOKEN, or None.

    An empty judge token is disabled. The admin token is checked first.
    """
    presented = token.strip()
    if not presented:
        return None
    if _same_token(presented, settings.demo_agent_token.strip()):
        return "admin"
    if _same_token(presented, settings.demo_judge_token.strip()):
        return "judge"
    return None


def is_agent(settings: Settings, token: str) -> bool:
    return agent_role(settings, token) is not None
