# ruff: noqa: E501
"""Customer-isolation tests for access.get_transactions (duckdb gold + sqlite app slice)."""

import os
import random
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from access import AccessError, get_transactions
from common import SEED, SLICE, connect

con = connect(read_only=True)
rng = random.Random(SEED)
SAMPLE = [
    r[0]
    for r in con.execute(
        f"SELECT customer_key FROM (SELECT DISTINCT customer_key FROM gold.transactions_masked) USING SAMPLE 60 ROWS (reservoir, {SEED})"
    ).fetchall()
]
con.close()


def _check_backend(backend, keys):
    for k in keys:
        rows = get_transactions(k, backend=backend)
        assert rows, k
        assert all(r["customer_key"] == k for r in rows)
    a, b = keys[0], keys[1]
    ra = {r["transaction_key"] for r in get_transactions(a, backend=backend)}
    rb = {r["transaction_key"] for r in get_transactions(b, backend=backend)}
    assert ra and rb and not (ra & rb)


def test_only_own_rows_duckdb():
    _check_backend("duckdb", SAMPLE)
    c = connect(read_only=True)
    for k in SAMPLE[:20]:
        n = c.execute(
            "SELECT count(*) FROM gold.transactions_masked WHERE customer_key=?", [k]
        ).fetchone()[0]
        assert n == len(get_transactions(k)), k
    c.close()


def test_forged_well_formed_key_returns_nothing():
    for _ in range(20):
        forged = "CUS_" + secrets.token_hex(10)
        assert get_transactions(forged) == []


def test_malformed_and_injection_keys_rejected():
    bad = [
        "",
        None,
        123,
        ["CUS_0"],
        "CUS_%",
        "CUS_' OR '1'='1",
        SAMPLE[0] + "' OR customer_key IS NOT NULL --",
        SAMPLE[0].upper(),
        " " + SAMPLE[0],
        SAMPLE[0] + "\n",
        "CLI-ZC7D4OHIPSUY",
        "*",
        "CUS_" + "g" * 20,
    ]
    for k in bad:
        try:
            get_transactions(k)
            raise AssertionError(f"accepted {k!r}")
        except AccessError:
            pass


def test_other_customer_key_never_returns_callers_rows():
    me, other = SAMPLE[2], SAMPLE[3]
    mine = {r["transaction_key"] for r in get_transactions(me)}
    theirs = get_transactions(other)
    assert all(r["customer_key"] == other for r in theirs)
    assert not (mine & {r["transaction_key"] for r in theirs})


def test_sqlite_slice():
    if not os.path.exists(SLICE):
        return
    import sqlite3

    keys = [
        r[0]
        for r in sqlite3.connect(SLICE)
        .execute("SELECT customer_key FROM customers ORDER BY customer_key LIMIT 40")
        .fetchall()
    ]
    _check_backend("sqlite", keys)
    assert get_transactions("CUS_" + secrets.token_hex(10), backend="sqlite") == []


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, str(e)[:300])
    sys.exit(1 if fails else 0)
