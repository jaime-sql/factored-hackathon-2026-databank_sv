# ruff: noqa: E501
"""SILVER: enforce schema contract (fail on drift), cast types, normalize country labels, dedupe, add UTC/local timestamps."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import TS_OFFSET_HOURS, connect
from contract import CONTRACT, COUNTRY_COLUMNS, COUNTRY_MAP, ContractError

META = {"_source_file", "_loaded_at"}


def check_and_cast(con, t, spec):
    bcols = [r[0] for r in con.execute(f"DESCRIBE bronze.{t}").fetchall() if r[0] not in META]
    want = list(spec["columns"])
    missing, extra = sorted(set(want) - set(bcols)), sorted(set(bcols) - set(want))
    if missing or extra:
        raise ContractError(f"{t}: schema drift. missing={missing} extra={extra}")
    # every non-null, non-empty bronze value must cast
    fails = {}
    for c, ty in spec["columns"].items():
        src = f"nullif(trim(\"{c}\"), '')"
        if ty == "BOOLEAN":
            expr = f"CASE lower({src}) WHEN 'true' THEN true WHEN 'false' THEN false END"
        else:
            expr = f"TRY_CAST({src} AS {ty})"
        n = con.execute(
            f"SELECT count(*) FROM bronze.{t} WHERE {src} IS NOT NULL AND ({expr}) IS NULL"
        ).fetchone()[0]
        if n:
            fails[c] = n
    if fails:
        raise ContractError(f"{t}: values failing type cast: {fails}")
    sel = []
    for c, ty in spec["columns"].items():
        src = f"nullif(trim(\"{c}\"), '')"
        if ty == "BOOLEAN":
            e = f"CASE lower({src}) WHEN 'true' THEN true WHEN 'false' THEN false END"
        else:
            e = f"CAST({src} AS {ty})"
        if c in COUNTRY_COLUMNS.get(t, []):
            cases = " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in COUNTRY_MAP.items())
            unknown = con.execute(
                f"SELECT list(DISTINCT {src}) FROM bronze.{t} WHERE {src} IS NOT NULL AND {src} NOT IN ({','.join(repr(k) for k in COUNTRY_MAP)})"
            ).fetchone()[0]
            if unknown:
                raise ContractError(f"{t}.{c}: unmapped country values {unknown}")
            e = f"CASE {src} {cases} END"
        sel.append(f'{e} AS "{c}"')
    return ", ".join(sel)


def run():
    con = connect()
    con.execute("CREATE SCHEMA IF NOT EXISTS silver")
    log = {"ts_offset_hours": TS_OFFSET_HOURS, "tables": {}}
    for t, spec in CONTRACT.items():
        sel = check_and_cast(con, t, spec)
        pk = ", ".join(spec["pk"])
        con.execute(
            f"CREATE OR REPLACE TEMP TABLE typed AS SELECT {sel}, _source_file FROM bronze.{t}"
        )
        n_in = con.execute("SELECT count(*) FROM typed").fetchone()[0]
        cols = ", ".join(f'"{c}"' for c in spec["columns"])
        n_exact = (
            n_in
            - con.execute(f"SELECT count(*) FROM (SELECT DISTINCT {cols} FROM typed)").fetchone()[0]
        )
        n_conflict = con.execute(
            f"""SELECT count(*) FROM (SELECT {pk} FROM (SELECT DISTINCT {cols} FROM typed) GROUP BY ALL HAVING count(*)>1)"""
        ).fetchone()[0]
        order = (
            "process_date DESC, _source_file DESC"
            if "process_date" in spec["columns"]
            else "_source_file DESC"
        )
        extra = ""
        if t == "transactions":
            extra = f", transaction_date AS transaction_ts_utc, transaction_date - INTERVAL {TS_OFFSET_HOURS} HOUR AS transaction_ts_local"
        # dedupe: exact duplicates dropped; PK conflicts keep the latest-arriving version (logged)
        con.execute(f"""CREATE OR REPLACE TABLE silver.{t} AS SELECT * EXCLUDE (_rn, _source_file) {extra} FROM (
            SELECT *, row_number() OVER (PARTITION BY {pk} ORDER BY {order}) _rn FROM typed) WHERE _rn = 1""")
        # post-conditions
        for c in spec["not_null"]:
            n = con.execute(f'SELECT count(*) FROM silver.{t} WHERE "{c}" IS NULL').fetchone()[0]
            if n:
                raise ContractError(f"{t}.{c}: {n} nulls in NOT NULL column")
        for c, vals in spec["enums"].items():
            bad = con.execute(
                f'SELECT list(DISTINCT "{c}") FROM silver.{t} WHERE "{c}" IS NOT NULL AND "{c}" NOT IN ({",".join(repr(v) for v in vals)})'
            ).fetchone()[0]
            if bad:
                raise ContractError(f"{t}.{c}: values outside contract {bad}")
        for c, (lo, hi) in spec["ranges"].items():
            n = con.execute(
                f'SELECT count(*) FROM silver.{t} WHERE "{c}" < {lo} OR "{c}" > {hi}'
            ).fetchone()[0]
            if n:
                raise ContractError(f"{t}.{c}: {n} values outside [{lo},{hi}]")
        if t == "transactions":
            lo, hi = con.execute(
                "SELECT min(transaction_ts_local - CAST(process_date AS TIMESTAMP)), max(transaction_ts_local - CAST(process_date AS TIMESTAMP)) FROM silver.transactions"
            ).fetchone()
            if lo.total_seconds() < 0 or hi.total_seconds() > 86400:
                raise ContractError(
                    f"transactions: local timestamp not inside process_date (offset assumption broken): {lo}..{hi}"
                )
        if t == "transactions":
            log["ts_boundary_rows_local_eq_next_midnight"] = con.execute(
                "SELECT count(*) FROM silver.transactions WHERE transaction_ts_local = CAST(process_date AS TIMESTAMP) + INTERVAL 1 DAY"
            ).fetchone()[0]
        n_out = con.execute(f"SELECT count(*) FROM silver.{t}").fetchone()[0]
        log["tables"][t] = {
            "bronze_rows": n_in,
            "exact_duplicates_dropped": n_exact,
            "pk_conflicts": n_conflict,
            "silver_rows": n_out,
        }
        print(
            f"silver.{t}: {n_in:,} -> {n_out:,} (exact dups {n_exact:,}, pk conflicts {n_conflict:,})"
        )
    con.execute(
        "CREATE OR REPLACE TABLE silver._run_log AS SELECT ? AS log_json, current_timestamp AS run_at",
        [json.dumps(log)],
    )
    con.close()
    return log


if __name__ == "__main__":
    run()
