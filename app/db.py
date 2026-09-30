"""Postgres connections for the app_rw role.

DATABASE_URL is read from the environment by Settings. This module never
logs the URL and never opens the eval schema.
"""

from __future__ import annotations

from typing import Any

APP_ROLE = "app_rw"
STATEMENT_TIMEOUT = "15s"
SEARCH_PATH = "app, public"

_role_ok: set[str] = set()


def connect_app(dsn: str) -> Any:
    if not dsn.strip():
        raise RuntimeError("DATABASE_URL is empty; SQLite is the local default")
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(
        dsn,
        row_factory=dict_row,
        connect_timeout=5,
        options=f"-c statement_timeout={STATEMENT_TIMEOUT} -c search_path={SEARCH_PATH}",
    )
    conn.execute("SET statement_timeout = %s", (STATEMENT_TIMEOUT,))
    conn.execute("SET search_path TO app, public")
    fingerprint = str(id(dsn))
    if fingerprint not in _role_ok:
        row = conn.execute(
            "SELECT current_user AS role_name, rolsuper, rolbypassrls "
            "FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        if row is None:
            conn.close()
            raise RuntimeError("DATABASE_URL must connect as the app_rw role, not the owner")
        role_name = str(row["role_name"])
        if role_name != APP_ROLE or bool(row["rolsuper"]) or bool(row["rolbypassrls"]):
            conn.close()
            raise RuntimeError("DATABASE_URL must connect as the app_rw role, not the owner")
        _role_ok.add(fingerprint)
    return conn
