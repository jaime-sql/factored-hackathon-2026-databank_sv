from __future__ import annotations

import psycopg
import pytest

from app.db import STATEMENT_TIMEOUT, connect_app


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
