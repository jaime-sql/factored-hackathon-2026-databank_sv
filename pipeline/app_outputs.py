# ruff: noqa: E501
"""Synthetic duplicate-charge fixture + masked SQLite app slice (both from gold, fixed seed)."""

import json
import os
import random
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
import gold
from common import FIXTURES, SEED, SLICE, connect

N_CASES = 300
TRUE_DUP_SHARE = 0.6
PER_COUNTRY = {"pending": 150, "reversed": 100, "high_score": 100, "random": 150}


def select_slice_customers(con):
    """Deterministic stratified pick per customer_country: customers with Pending, Reversed, fraud_score>=30, plus random."""
    con.execute(f"""CREATE OR REPLACE TEMP TABLE cust_flags AS
        SELECT customer_key, any_value(customer_country) country,
               bool_or(transaction_status='Pending') has_pending, bool_or(transaction_status='Reversed') has_reversed,
               bool_or(fraud_score >= 30) has_high, sha256('{SEED}:' || customer_key) h
        FROM gold.transactions_masked GROUP BY 1""")
    parts = []
    for flag, n in PER_COUNTRY.items():
        cond = {
            "pending": "has_pending",
            "reversed": "has_reversed",
            "high_score": "has_high",
            "random": "true",
        }[flag]
        parts.append(f"""SELECT customer_key, '{flag}' AS reason FROM (SELECT customer_key, row_number() OVER (PARTITION BY country ORDER BY h) rn
                         FROM cust_flags WHERE {cond}) WHERE rn <= {n}""")
    con.execute(
        f"CREATE OR REPLACE TEMP TABLE slice_customers AS SELECT customer_key, min(reason) reason FROM ({' UNION ALL '.join(parts)}) GROUP BY 1"
    )


def build_fixture(con):
    rng = random.Random(SEED)
    src = con.execute(f"""SELECT t.* FROM gold.transactions_masked t JOIN slice_customers s USING (customer_key)
        WHERE t.merchant_name IS NOT NULL AND t.amount > 0 AND t.transaction_status = 'Approved'
        ORDER BY sha256('{SEED}:fx:' || t.transaction_key) LIMIT {N_CASES}""").fetchdf()
    rows = []
    for i, r in enumerate(src.to_dict("records")):
        case = f"SYNCASE_{i:04d}"
        true_dup = rng.random() < TRUE_DUP_SHARE
        delta = (
            rng.randint(5, 180) if true_dup else rng.randint(300, 1800)
        )  # seconds after the original
        base = {k: r[k] for k in gold.MASKED_COLUMNS}
        a = dict(base, transaction_key=f"SYN_{i:04d}_A", role="original", seconds_after_original=0)
        b = dict(
            base, transaction_key=f"SYN_{i:04d}_B", role="repeat", seconds_after_original=delta
        )
        import datetime as dt

        b["transaction_ts_utc"] = r["transaction_ts_utc"] + dt.timedelta(seconds=delta)
        b["transaction_ts_local"] = r["transaction_ts_local"] + dt.timedelta(seconds=delta)
        if (
            not true_dup and rng.random() < 0.5
        ):  # legit repeats sometimes come through a different channel
            b["channel"] = rng.choice([c for c in ("POS", "App", "Web") if c != r["channel"]])
        for x in (a, b):
            x.update(
                case_id=case,
                scenario="true_duplicate" if true_dup else "legitimate_repeat",
                is_synthetic=True,
                source_transaction_key=r["transaction_key"],
                is_fraud=None,
            )
        rows += [a, b]
    import pandas as pd

    df = pd.DataFrame(rows)
    cols = [
        "case_id",
        "scenario",
        "role",
        "is_synthetic",
        "seconds_after_original",
        "source_transaction_key",
    ] + gold.MASKED_COLUMNS
    df = df[cols]
    os.makedirs(FIXTURES, exist_ok=True)
    con.register("fx_df", df)
    con.execute(
        f"COPY (SELECT * FROM fx_df ORDER BY case_id, role) TO '{os.path.join(FIXTURES, 'synthetic_duplicates.parquet')}' (FORMAT parquet)"
    )
    con.execute(
        f"COPY (SELECT * FROM fx_df ORDER BY case_id, role) TO '{os.path.join(FIXTURES, 'synthetic_duplicates.csv')}' (HEADER)"
    )
    return df


def build_slice(con, fx):
    if os.path.exists(SLICE):
        os.remove(SLICE)
    tx = con.execute("""SELECT t.* EXCLUDE (transaction_ts_utc, transaction_ts_local, process_date),
            strftime(transaction_ts_utc, '%Y-%m-%d %H:%M:%S') transaction_ts_utc, strftime(transaction_ts_local, '%Y-%m-%d %H:%M:%S') transaction_ts_local,
            strftime(process_date, '%Y-%m-%d') process_date, CAST(amount AS DOUBLE) amount_d, CAST(amount_usd AS DOUBLE) amount_usd_d, CAST(fraud_score AS DOUBLE) fraud_score_d
        FROM gold.transactions_masked t JOIN slice_customers USING (customer_key)""").fetchdf()
    tx = tx.drop(columns=["amount", "amount_usd", "fraud_score"]).rename(
        columns={"amount_d": "amount", "amount_usd_d": "amount_usd", "fraud_score_d": "fraud_score"}
    )
    cu = con.execute("""SELECT c.customer_key, c.customer_country, c.customer_segment, c.customer_accent, s.reason AS slice_reason
        FROM gold.customers_masked c JOIN slice_customers s USING (customer_key)""").fetchdf()
    fx2 = fx.copy()
    for c in ("transaction_ts_utc", "transaction_ts_local"):
        fx2[c] = fx2[c].astype(str)
    fx2["process_date"] = fx2["process_date"].astype(str)
    for c in ("amount", "amount_usd", "fraud_score"):
        fx2[c] = fx2[c].astype(float)
    db = sqlite3.connect(SLICE)
    cu.to_sql("customers", db, index=False)
    tx.to_sql("transactions", db, index=False)
    fx2.to_sql("synthetic_duplicates", db, index=False)
    db.executescript("""CREATE INDEX ix_tx_customer ON transactions(customer_key);
        CREATE UNIQUE INDEX ix_tx_key ON transactions(transaction_key);
        CREATE INDEX ix_syn_customer ON synthetic_duplicates(customer_key);
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);""")
    db.executemany(
        "INSERT INTO meta VALUES (?,?)",
        [
            ("seed", str(SEED)),
            ("source", "gold.transactions_masked (pseudonymous, masked)"),
            (
                "synthetic_duplicates",
                "is_synthetic=1 rows only; never mix into model training/evaluation",
            ),
            (
                "timestamps",
                "transaction_ts_utc = raw transaction_date; transaction_ts_local = utc - 6h",
            ),
        ],
    )
    db.commit()
    db.execute("VACUUM")
    db.close()


def run():
    con = connect()
    select_slice_customers(con)
    fx = build_fixture(con)
    build_slice(con, fx)
    s = sqlite3.connect(SLICE)
    stats = {
        "fixture_rows": len(fx),
        "fixture_cases": fx.case_id.nunique(),
        "fixture_scenarios": fx.groupby("scenario").case_id.nunique().to_dict(),
        "slice_customers": s.execute("SELECT count(*) FROM customers").fetchone()[0],
        "slice_customers_by_country": dict(
            s.execute("SELECT customer_country, count(*) FROM customers GROUP BY 1").fetchall()
        ),
        "slice_transactions": s.execute("SELECT count(*) FROM transactions").fetchone()[0],
        "slice_status": dict(
            s.execute("SELECT transaction_status, count(*) FROM transactions GROUP BY 1").fetchall()
        ),
        "slice_fraud_score_ge30": s.execute(
            "SELECT count(*) FROM transactions WHERE fraud_score >= 30"
        ).fetchone()[0],
        "slice_fraud_score_lt10": s.execute(
            "SELECT count(*) FROM transactions WHERE fraud_score < 10"
        ).fetchone()[0],
        "slice_is_fraud": s.execute("SELECT count(*) FROM transactions WHERE is_fraud").fetchone()[
            0
        ],
        "slice_mb": round(os.path.getsize(SLICE) / 1e6, 2),
    }
    s.close()
    con.close()
    json.dump(
        stats, open(os.path.join(FIXTURES, "app_outputs_stats.json"), "w"), indent=1, default=str
    )
    print(json.dumps(stats, indent=1, default=str))


if __name__ == "__main__":
    run()
