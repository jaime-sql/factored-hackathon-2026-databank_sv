# ruff: noqa: E501
#!/usr/bin/env python3
"""Repeatable load of the masked demo data into Supabase project factored-hackathon-2026 (ref dmqwgbtrrnxkgcahunrc).

Sources (all local, all masked):
  app_slice.sqlite (customers, transactions, meta), fixtures/synthetic_duplicates.parquet,
  cache/pipeline.duckdb gold.fraud_features (identical to Databricks workspace.gold.fraud_features) filtered to slice keys.
Target: public.{customers, transactions (without is_fraud), synthetic_duplicates, meta, fraud_features}, eval.transaction_labels.

Connection (from env only; nothing is printed or written):
  SUPABASE_DB_URL  postgres URI (session pooler or direct), used with COPY.  e.g. export SUPABASE_DB_URL='postgresql://...'
Usage:  .venv/bin/python pipeline/load_supabase.py [--dry-run]
The script applies pipeline/supabase_schema.sql (idempotent), truncates the target tables, bulk-loads them, then verifies counts.
"""

import argparse
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import DB, FIXTURES, SLICE

TARGET_REF = "dmqwgbtrrnxkgcahunrc"
FORBIDDEN_REFS = ["kwbhytabavegnqfeidjw"]  # iglesiaSJB: never touch
FEATURE_LIST = os.environ.get("FEATURE_LIST", "/workspace/hack-ml/artifacts/feature_list.json")
PII = re.compile(r"(\b(CLI|PRD|TRX)-[A-Z0-9]{8,})|([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,})")

# Customer local-clock zone: country default, overridden by CITY_TZ
COUNTRY_TZ = {
    "Argentina": "America/Argentina/Buenos_Aires",
    "Colombia": "America/Bogota",
    "Mexico": "America/Mexico_City",
}

# City overrides where the customer's local clock differs from the country default (city is read locally, never loaded)
CITY_TZ = {("Mexico", "Tijuana"): "America/Tijuana"}


def customer_cities(keys):
    """Map customer_key -> city from local silver.customers via the salted pseudonym (salt from .env; nothing printed)."""
    import duckdb
    from common import pseudo_sql, salt

    g = duckdb.connect(DB, read_only=True)
    g.execute("CREATE TEMP TABLE ck(customer_key VARCHAR)")
    g.executemany("INSERT INTO ck VALUES (?)", [(k,) for k in keys])
    rows = g.execute(
        f"""SELECT ck.customer_key, c.city FROM (SELECT {pseudo_sql("customer_id", "customer")} AS customer_key, city
                         FROM silver.customers) c JOIN ck USING (customer_key)""",
        {"salt": salt()},
    ).fetchall()
    g.close()
    return dict(rows)


def sources():
    s = sqlite3.connect(f"file:{SLICE}?mode=ro", uri=True)

    def q(sql):
        cur = s.execute(sql)
        return [d[0] for d in cur.description], cur.fetchall()

    out = {}
    cc, cr = q(
        "SELECT customer_key, customer_country, customer_segment, customer_accent, slice_reason FROM customers"
    )
    unmapped = sorted({r[1] for r in cr if r[1] not in COUNTRY_TZ}, key=str)
    if unmapped:
        raise SystemExit(f"unmapped customer_country values (no tz rule): {unmapped}")
    city = customer_cities([r[0] for r in cr])
    missing = [k for k in (r[0] for r in cr) if k not in city]
    if missing:
        raise SystemExit(
            f"{len(missing)} slice customers not found in local silver.customers; cannot derive tz"
        )
    out["customers"] = (
        cc + ["tz"],
        [tuple(r) + (CITY_TZ.get((r[1], city[r[0]]), COUNTRY_TZ[r[1]]),) for r in cr],
    )
    tx_cols = [r[1] for r in s.execute("PRAGMA table_info(transactions)")]
    keep = [c for c in tx_cols if c != "is_fraud"]
    out["transactions"] = q(f"SELECT {', '.join(keep)} FROM transactions")
    lc, lr = q("SELECT transaction_key, is_fraud FROM transactions")
    out["eval.transaction_labels"] = (lc, [(k, bool(v)) for k, v in lr])
    out["meta"] = q("SELECT key, value FROM meta")
    import duckdb

    d = duckdb.connect()
    fx = os.path.join(FIXTURES, "synthetic_duplicates.parquet")
    syn_cols = [r[1] for r in s.execute("PRAGMA table_info(synthetic_duplicates)")]
    cur = d.execute(f"""SELECT {
        ", ".join(
            "CAST(transaction_ts_utc AS VARCHAR)"
            if c == "transaction_ts_utc"
            else "CAST(transaction_ts_local AS VARCHAR)"
            if c == "transaction_ts_local"
            else "CAST(process_date AS VARCHAR)"
            if c == "process_date"
            else "CAST(is_synthetic AS INTEGER)"
            if c == "is_synthetic"
            else "CAST(is_fraud AS VARCHAR)"
            if c == "is_fraud"
            else f"CAST({c} AS DOUBLE)"
            if c in ("amount", "amount_usd", "fraud_score")
            else c
            for c in syn_cols
        )
    }
                        FROM read_parquet('{fx}') ORDER BY case_id, role""")
    out["synthetic_duplicates"] = (syn_cols, cur.fetchall())
    feats = json.load(open(FEATURE_LIST))["features"]
    fcols = ["transaction_key"] + feats + ["split"]
    assert "is_fraud" not in fcols
    g = duckdb.connect(DB, read_only=True)
    keys = [r[0] for r in out["transactions"][1]]
    g.execute("CREATE TEMP TABLE k(transaction_key VARCHAR)")
    g.executemany("INSERT INTO k VALUES (?)", [(x,) for x in keys])
    cur = g.execute(
        f"SELECT {', '.join('f.' + c for c in fcols)} FROM gold.fraud_features f JOIN k USING (transaction_key) ORDER BY 1"
    )
    out["fraud_features"] = (fcols, cur.fetchall())
    return out


UTC = __import__("datetime").timezone.utc
LOCAL = __import__("datetime").timezone(__import__("datetime").timedelta(hours=-6))
META_TIMESTAMPS = (
    "transaction_ts_utc and transaction_ts_local are timestamptz of the same instant "
    "(local source values were UTC-6 wall clock); process_date is a UTC-6 date"
)


def typed(data):
    """Parse ISO text into tz-aware datetimes / dates so COPY never depends on the session TimeZone.
    transaction_ts_utc -> UTC; transaction_ts_local -> UTC-6 (documented offset); process_date -> date. Fails loudly on bad values."""
    import datetime as dt

    conv = {
        "transaction_ts_utc": lambda v: dt.datetime.fromisoformat(v).replace(tzinfo=UTC),
        "transaction_ts_local": lambda v: dt.datetime.fromisoformat(v).replace(tzinfo=LOCAL),
        "process_date": lambda v: (
            dt.date.fromisoformat(v[:10])
            if (len(v) == 10 or v[10:] == " 00:00:00")
            else (_ for _ in ()).throw(ValueError(f"process_date not a whole day: {v}"))
        ),
    }
    out = {}
    for t, (cols, rows) in data.items():
        idx = [(i, conv[c]) for i, c in enumerate(cols) if c in conv]
        if t == "meta":
            rows = [(k, META_TIMESTAMPS if k == "timestamps" else v) for k, v in rows]
        elif idx:
            new = []
            for r in rows:
                r = list(r)
                for i, f in idx:
                    if r[i] is not None:
                        if getattr(r[i], "tzinfo", None) is not None:
                            raise ValueError(f"{t}: unexpected tz-aware source value")
                        r[i] = f(str(r[i]))
                new.append(tuple(r))
            rows = new
        out[t] = (cols, rows)
    return out


def pii_scan(data):
    bad = 0
    for t, (cols, rows) in data.items():
        for r in rows:
            for v in r:
                if isinstance(v, str) and PII.search(v):
                    bad += 1
    return bad


TS_COLS = ("transaction_ts_utc", "transaction_ts_local", "process_date")
ORDER = [
    "customers",
    "transactions",
    "eval.transaction_labels",
    "synthetic_duplicates",
    "meta",
    "fraud_features",
]


def tname(t):
    return t if "." in t else f"public.{t}"


def load(url, data):
    import psycopg

    with psycopg.connect(url, autocommit=False) as con:
        with con.cursor() as cur:
            cur.execute(open(os.path.join(os.path.dirname(__file__), "supabase_schema.sql")).read())
            cur.execute(
                "TRUNCATE public.fraud_features, eval.transaction_labels, public.synthetic_duplicates, public.transactions, public.customers, public.meta"
            )
            for t in ORDER:
                cols, rows = data[t]
                with cur.copy(f"COPY {tname(t)} ({', '.join(cols)}) FROM STDIN") as cp:
                    for r in rows:
                        cp.write_row(r)
            con.commit()
            res = {}
            for t in ORDER:
                cur.execute(f"SELECT count(*) FROM {tname(t)}")
                res[t] = cur.fetchone()[0]
            cur.execute("""SELECT t.transaction_status, count(*), count(f.transaction_key) FROM public.transactions t
                           LEFT JOIN public.fraud_features f USING (transaction_key) GROUP BY 1 ORDER BY 1""")
            res["feature_coverage_by_status"] = cur.fetchall()
            res["ts_checks"] = {}
            for t in ("transactions", "synthetic_duplicates"):
                cur.execute(f"""SELECT count(*) FILTER (WHERE transaction_ts_utc IS NULL OR transaction_ts_local IS NULL OR process_date IS NULL),
                    count(*) FILTER (WHERE transaction_ts_utc <> transaction_ts_local),
                    count(*) FILTER (WHERE (transaction_ts_local AT TIME ZONE 'UTC' - interval '6 hours')::date <> process_date),
                    min(transaction_ts_utc)::text, max(transaction_ts_utc)::text,
                    (SELECT data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='{t}' AND column_name='transaction_ts_utc')
                    FROM public.{t}""")
                res["ts_checks"][t] = cur.fetchone()
            cur.execute(
                "SELECT customer_country, tz, count(*) FROM public.customers GROUP BY 1,2 ORDER BY 1"
            )
            res["tz_dist"] = cur.fetchall()
            cur.execute(
                "SELECT count(*) FROM public.customers WHERE tz IS NULL OR tz NOT IN (SELECT name FROM pg_timezone_names)"
            )
            res["tz_bad"] = cur.fetchone()[0]
            cur.execute("""SELECT n.nspname||'.'||c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                           WHERE n.nspname IN ('public','eval') AND c.relkind='r' ORDER BY 1""")
            res["rls"] = cur.fetchall()
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    data = sources()
    src = {t: len(r) for t, (c, r) in data.items()}
    n_pii = pii_scan(data)
    print("source rows:", json.dumps(src))
    print("PII/raw-id matches in source values:", n_pii)
    if n_pii:
        raise SystemExit("PII check failed; refusing to load")
    data = typed(data)
    nulls_src = {
        t: sum(1 for r in rows for i, c in enumerate(cols) if c in TS_COLS and r[i] is None)
        for t, (cols, rows) in data.items()
    }
    print("timestamp/date values parsed; NULLs in source timestamp columns:", json.dumps(nulls_src))
    if a.dry_run:
        return
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise SystemExit(
            "SUPABASE_DB_URL not set (postgres URI for project %s); nothing loaded" % TARGET_REF  # noqa: UP031
        )
    if any(r in url for r in FORBIDDEN_REFS):
        raise SystemExit("refusing: URL points at a forbidden project")
    if TARGET_REF not in url and not os.environ.get("ALLOW_OTHER_TARGET"):
        raise SystemExit(
            f"refusing: URL does not reference project {TARGET_REF} (set ALLOW_OTHER_TARGET=1 for a local test DB)"
        )
    res = load(url, data)
    ok = all(res[t] == src[t] for t in ORDER)
    print("counts:", "ok" if ok else "MISMATCH")
    print("loaded rows:", json.dumps({t: res[t] for t in ORDER}))
    print("counts match source:", ok)
    print("feature coverage (status, tx, with features):", res["feature_coverage_by_status"])
    print("rls:", res["rls"])
    print(
        "timestamp checks (nulls, utc<>local instants, local day<>process_date, min, max, type):",
        res["ts_checks"],
    )
    print("customer tz distribution:", res["tz_dist"], "| NULL/invalid tz:", res["tz_bad"])
    ok = (
        ok
        and all(v[0] == 0 and v[1] == 0 for v in res["ts_checks"].values())
        and res["tz_bad"] == 0
    )
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
