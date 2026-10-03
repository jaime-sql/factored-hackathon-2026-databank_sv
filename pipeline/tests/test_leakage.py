# ruff: noqa: E501
"""Leakage tests for gold.fraud_features and splits_manifest.json."""

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gold
from common import FIXTURES, ROOT, SEED, connect, sha256_ids

M = json.load(open(os.path.join(ROOT, "splits_manifest.json")))
con = connect(read_only=True)
T = "gold.fraud_features"


def test_split_time_ordering():
    c1, c2 = M["cutoff_train_end"], M["cutoff_val_end"]
    assert (
        con.execute(
            f"SELECT count(*) FROM {T} WHERE split='test' AND transaction_ts_utc < TIMESTAMP '{c1}'"
        ).fetchone()[0]
        == 0
    )
    assert (
        con.execute(
            f"SELECT count(*) FROM {T} WHERE split='test' AND transaction_ts_utc < TIMESTAMP '{c2}'"
        ).fetchone()[0]
        == 0
    )
    assert (
        con.execute(
            f"SELECT count(*) FROM {T} WHERE split='val' AND transaction_ts_utc < TIMESTAMP '{c1}'"
        ).fetchone()[0]
        == 0
    )
    assert (
        con.execute(
            f"SELECT count(*) FROM {T} WHERE split='train' AND transaction_ts_utc >= TIMESTAMP '{c1}'"
        ).fetchone()[0]
        == 0
    )
    mx_train, mn_test = con.execute(
        f"SELECT max(transaction_ts_utc) FILTER (WHERE split='train'), min(transaction_ts_utc) FILTER (WHERE split='test') FROM {T}"
    ).fetchone()
    assert mx_train < mn_test


def test_no_excluded_columns():
    cols = {r[0] for r in con.execute(f"DESCRIBE {T}").fetchall()}
    bad = cols & set(gold.FORBIDDEN_IN_MODEL)
    assert not bad, bad
    allowed = set(
        gold.ID_COLUMNS
        + gold.FEATURES_NUMERIC
        + gold.FEATURES_CATEGORICAL
        + [gold.LABEL, gold.BASELINE]
        + gold.SLICE_COLUMNS
    )
    assert cols == allowed, cols ^ allowed


def test_ml_scope_excludes_pending_reversed():
    n = con.execute(f"""SELECT count(*) FROM {T} f JOIN gold.transactions_masked t USING (transaction_key)
                        WHERE t.transaction_status IN ('Pending','Reversed')""").fetchone()[0]
    assert n == 0


def test_manifest_hashes():
    for sp, meta in M["splits"].items():
        ids = [
            r[0]
            for r in con.execute(f"SELECT transaction_key FROM {T} WHERE split=?", [sp]).fetchall()
        ]
        assert len(ids) == meta["rows"] and sha256_ids(ids) == meta["sha256_sorted_ids"], sp
    assert (
        con.execute(f"SELECT count(*) - count(DISTINCT transaction_key) FROM {T}").fetchone()[0]
        == 0
    )


def test_history_uses_only_strictly_earlier_rows():
    rng = random.Random(SEED)  # noqa: F841
    keys = [
        r[0]
        for r in con.execute(
            f"SELECT transaction_key FROM {T} USING SAMPLE 300 ROWS (reservoir, {SEED})"
        ).fetchall()
    ]
    for k in keys:
        f = con.execute(
            f"SELECT customer_key, transaction_ts_utc, prior_tx_count, prior_tx_count_24h, secs_since_prev_tx, prior_count_same_merchant, merchant_name FROM {T} WHERE transaction_key=?",
            [k],
        ).fetchone()
        ck, ts, n_all, n24, gap, n_mer, mer = f
        exp = con.execute(
            """SELECT count(*), count(*) FILTER (WHERE transaction_ts_utc >= ?::TIMESTAMP - INTERVAL 24 HOUR),
                   date_diff('second', max(transaction_ts_utc), ?::TIMESTAMP),
                   count(*) FILTER (WHERE merchant_name = ?)
            FROM gold.transactions_masked WHERE customer_key=? AND transaction_ts_utc < ?""",
            [ts, ts, mer, ck, ts],
        ).fetchone()
        assert (n_all, n24, gap) == exp[:3], (k, (n_all, n24, gap), exp)
        if mer is not None:
            assert n_mer == exp[3], (k, n_mer, exp[3])


def test_synthetic_fixture_not_in_splits():
    p = os.path.join(FIXTURES, "synthetic_duplicates.parquet")
    if not os.path.exists(p):
        return
    n = con.execute(
        f"SELECT count(*) FROM read_parquet('{p}') s JOIN {T} f USING (transaction_key)"
    ).fetchone()[0]
    assert n == 0


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
