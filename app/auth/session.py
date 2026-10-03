"""Customer session cookies and the local agent token.

The eval runner uses a separate header, checked in eval_access.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from app.config import Settings


def sign_customer(secret: str, customer_key: str, ttl_hours: int, *, is_test: bool = False) -> str:
    exp = int(time.time()) + ttl_hours * 3600
    flag = "1" if is_test else "0"
    body = f"{customer_key}.{exp}.{flag}"
    digest = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"cust.{body}.{digest}"


def sign_test_marker(secret: str, ttl_hours: int) -> str:
    exp = int(time.time()) + ttl_hours * 3600
    body = f"test.{exp}"
    digest = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{digest}"


def read_session(secret: str, token: str) -> tuple[str, bool] | None:
    """Return the customer key and the signed test-traffic flag.

    Older cookies have four parts and count as ordinary traffic.
    """
    parts = token.split(".")
    if not parts or parts[0] != "cust":
        return None
    if len(parts) == 4:
        customer_key, exp, digest = parts[1], parts[2], parts[3]
        body = f"{customer_key}.{exp}"
        is_test = False
    elif len(parts) == 5 and parts[3] in {"0", "1"}:
        customer_key, exp, flag, digest = parts[1], parts[2], parts[3], parts[4]
        body = f"{customer_key}.{exp}.{flag}"
        is_test = flag == "1"
    else:
        return None
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if len(digest) != len(expected) or not hmac.compare_digest(digest, expected):
        return None
    try:
        expires = int(exp)
    except ValueError:
        return None
    if expires < int(time.time()):
        return None
    return customer_key, is_test


def read_customer(secret: str, token: str) -> str | None:
    session = read_session(secret, token)
    if session is None:
        return None
    return session[0]


def read_test_marker(secret: str, token: str) -> bool:
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "test":
        return False
    exp, digest = parts[1], parts[2]
    body = f"test.{exp}"
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if len(digest) != len(expected) or not hmac.compare_digest(digest, expected):
        return False
    try:
        expires = int(exp)
    except ValueError:
        return False
    return expires >= int(time.time())


def accepts_qa_test_token(expected: str, presented: str) -> bool:
    """True only when both sides are non-empty and match.

    An empty expected token disables the flag. The comparison hashes both
    values first so a wrong length does not skip the constant-time check.
    """
    left = presented.strip()
    right = expected.strip()
    if not left or not right:
        return False
    return hmac.compare_digest(
        hashlib.sha256(left.encode()).digest(),
        hashlib.sha256(right.encode()).digest(),
    )


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
