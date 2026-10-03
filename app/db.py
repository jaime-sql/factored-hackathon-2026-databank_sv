"""Postgres connections for the app_rw role.

DATABASE_URL is read from the environment by Settings. This module never
logs the URL and never opens the eval schema.

Each statement used to call psycopg.connect. Cloud Run spent 1.5–3s on that
handshake, so a queue listing that wrote one audit row per case timed out.
Idle connections go back to a process-local pool and are checked out again.
"""

from __future__ import annotations

import threading
from typing import Any

APP_ROLE = "app_rw"
STATEMENT_TIMEOUT = "15s"
SEARCH_PATH = "app,public"
_POOL_MAX = 4

_role_ok: set[str] = set()
_idle: dict[str, list[Any]] = {}
_lock = threading.Lock()


def reset_pool() -> None:
    """Drop idle connections. Tests use this so a fake connection cannot leak."""
    with _lock:
        leftover = [conn for bucket in _idle.values() for conn in bucket]
        _idle.clear()
        _role_ok.clear()
    for conn in leftover:
        try:
            conn.close()
        except Exception:
            pass


def connect_app(dsn: str) -> Any:
    if not dsn.strip():
        raise RuntimeError("DATABASE_URL is empty; SQLite is the local default")
    return _Lease(dsn, _checkout(dsn))


class _Lease:
    def __init__(self, dsn: str, conn: Any) -> None:
        self.dsn = dsn
        self.conn = conn

    def __enter__(self) -> Any:
        return self.conn

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        conn = self.conn
        if exc_type is not None or _transaction_open(conn):
            try:
                conn.rollback()
            except Exception:
                _discard(conn)
                return
        _release(self.dsn, conn)


def _checkout(dsn: str) -> Any:
    with _lock:
        bucket = _idle.get(dsn)
        while bucket:
            conn = bucket.pop()
            if not getattr(conn, "closed", False):
                return conn
    return _open(dsn)


def _release(dsn: str, conn: Any) -> None:
    if getattr(conn, "closed", False):
        return
    with _lock:
        bucket = _idle.setdefault(dsn, [])
        if len(bucket) < _POOL_MAX:
            bucket.append(conn)
            return
    _discard(conn)


def _discard(conn: Any) -> None:
    try:
        conn.close()
    except Exception:
        pass


def _transaction_open(conn: Any) -> bool:
    info = getattr(conn, "info", None)
    status = getattr(info, "transaction_status", None)
    if status is None:
        return False
    try:
        from psycopg.pq import TransactionStatus
    except Exception:
        return False
    return status != TransactionStatus.IDLE


def _open(dsn: str) -> Any:
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(
        dsn,
        row_factory=dict_row,
        connect_timeout=5,
        options=f"-c statement_timeout={STATEMENT_TIMEOUT} -c search_path={SEARCH_PATH}",
    )
    try:
        conn.execute("SET search_path TO app, public")
        if dsn not in _role_ok:
            row = conn.execute(
                "SELECT current_user AS role_name, rolsuper, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            ).fetchone()
            if row is None:
                raise RuntimeError("DATABASE_URL must connect as the app_rw role, not the owner")
            role_name = str(row["role_name"])
            if role_name != APP_ROLE or bool(row["rolsuper"]) or bool(row["rolbypassrls"]):
                raise RuntimeError("DATABASE_URL must connect as the app_rw role, not the owner")
            _role_ok.add(dsn)
    except Exception:
        _discard(conn)
        raise
    return conn
