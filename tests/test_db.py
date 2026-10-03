from __future__ import annotations

import psycopg
import pytest

from app.db import STATEMENT_TIMEOUT, connect_app, reset_pool


def test_search_path_option_has_no_space(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_connect(*_args: object, **kwargs: object) -> object:
        captured["options"] = str(kwargs["options"])
        raise RuntimeError("stop")

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    with pytest.raises(RuntimeError, match="stop"):
        connect_app("postgresql://app_rw@localhost/harbor")

    options = captured["options"]
    prefix = f"-c statement_timeout={STATEMENT_TIMEOUT} -c search_path="
    assert options.startswith(prefix)
    search_path = options.removeprefix(prefix)
    assert " " not in search_path
    assert search_path == "app,public"


def test_connect_app_reuses_a_pooled_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    opens = {"n": 0}

    class Cursor:
        def fetchone(self) -> dict[str, object]:
            return {"role_name": "app_rw", "rolsuper": False, "rolbypassrls": False}

    class Conn:
        closed = False

        def execute(self, *_args: object, **_kwargs: object) -> Cursor:
            return Cursor()

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    def fake_connect(*_args: object, **_kwargs: object) -> Conn:
        opens["n"] += 1
        return Conn()

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    dsn = "postgresql://app_rw@localhost/harbor_pool"
    reset_pool()
    try:
        with connect_app(dsn) as first:
            first.execute("SELECT 1")
        with connect_app(dsn) as second:
            second.execute("SELECT 1")
        assert first is second
        assert opens["n"] == 1
    finally:
        reset_pool()
