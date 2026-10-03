# ruff: noqa: E501
"""Export masked tables to Parquet for Databricks upload: gold under out/gold/ (run), masked bronze/silver under out/<layer>/ (run_layers)."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import FIXTURES, OUT, connect

GOLD_EXPORTS = {
    "transactions_masked": "SELECT * FROM gold.transactions_masked ORDER BY customer_key, transaction_ts_utc",
    "customers_masked": "SELECT * FROM gold.customers_masked ORDER BY customer_key",
    "fraud_features": "SELECT * FROM gold.fraud_features ORDER BY transaction_ts_utc, transaction_key",
    "fraud_splits": "SELECT transaction_key, split, transaction_ts_utc FROM gold.fraud_features ORDER BY transaction_ts_utc, transaction_key",
}


def run():
    con = connect(read_only=True)
    d = os.path.join(OUT, "gold")
    os.makedirs(d, exist_ok=True)
    files = {}
    for name, sql in GOLD_EXPORTS.items():
        p = os.path.join(d, f"{name}.parquet")
        con.execute(
            f"COPY ({sql}) TO '{p}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 500000)"
        )
        files[name] = p
    fx = os.path.join(FIXTURES, "synthetic_duplicates.parquet")
    if os.path.exists(fx):
        files["synthetic_duplicates"] = fx
    for n, p in files.items():
        print(n, round(os.path.getsize(p) / 1e6, 1), "MB")
    con.close()
    return files


if __name__ == "__main__":
    run()


# ---------------------------------------------------------------------------------------------------------------------------
# Masked copies of the bronze and silver layers (for Databricks visibility of all three layers). Nothing unmasked leaves the box:
# every column is on an explicit allow-list, raw ids become the same salted keys gold uses (so masked bronze/silver/gold join),
# and direct PII (names, document number/type, date of birth, gender, email, phones, address, postal code, customer city/state,
# product number, exact latitude/longitude, local file paths) is dropped. scan_masked_parquet() must pass before any upload.


def _bronze_key(col, kind):
    from common import pseudo_sql

    return pseudo_sql(f"nullif(trim({col}), '')", kind)


def _layer_sql(layer):
    """{table: SELECT} for one layer's masked export. Bronze stays all-VARCHAR as delivered; silver keeps its contract types."""
    from common import pseudo_sql

    src = f"{layer}"
    key = (lambda c, k: _bronze_key(c, k)) if layer == "bronze" else (lambda c, k: pseudo_sql(c, k))
    bmeta = (
        [r"regexp_replace(_source_file, '^.*/raw/', '') AS _source_file", "_loaded_at"]
        if layer == "bronze"
        else []
    )
    tx = [
        f"{key('transaction_id', 'transaction')} AS transaction_key",
        "transaction_date",
        "process_date",
        f"{key('product_id', 'product')} AS product_key",
        f"{key('customer_id', 'customer')} AS customer_key",
        "transaction_type",
        "transaction_category",
        "amount",
        "currency",
        "amount_usd",
        "channel",
        "branch_id",
        "merchant_name",
        "merchant_category",
        "transaction_country",
        "transaction_city",
        "transaction_status",
        "response_code",
        "is_fraud",
        "fraud_score",
    ]
    if layer == "silver":
        tx += ["transaction_ts_utc", "transaction_ts_local"]
    cu = [
        f"{key('customer_id', 'customer')} AS customer_key",
        "country",
        "detected_accent",
        "segment",
        "credit_score",
        "estimated_monthly_income",
        "occupation",
        "marital_status",
        "education_level",
        "registration_date",
        "registration_branch_id",
        "customer_status",
        "last_updated",
        "accepts_marketing",
    ]
    pr = [
        f"{key('product_id', 'product')} AS product_key",
        f"{key('customer_id', 'customer')} AS customer_key",
        "product_type",
        "currency",
        "current_balance",
        "credit_limit",
        "interest_rate",
        "opening_date",
        "expiration_date",
        "opening_branch_id",
        "product_status",
        "opening_channel",
        "has_linked_app",
        "days_past_due",
        "last_transaction_date",
        "last_updated",
    ]
    q = {
        "transactions_masked": f"SELECT {', '.join(tx + bmeta)} FROM {src}.transactions ORDER BY customer_key, transaction_date",
        "customers_masked": f"SELECT {', '.join(cu + bmeta)} FROM {src}.customers ORDER BY customer_key",
        "products_masked": f"SELECT {', '.join(pr + bmeta)} FROM {src}.products ORDER BY customer_key, product_key",
    }
    if layer == "silver":
        q["run_log"] = (
            "SELECT log_json, run_at FROM silver._run_log"  # counts/offsets only, no row data
        )
    return q


LAYER_SOURCE = {
    "transactions_masked": "transactions",
    "customers_masked": "customers",
    "products_masked": "products",
    "run_log": "_run_log",
}
DROPPED_BY_TABLE = {
    "transactions": [
        "transaction_id -> transaction_key",
        "product_id -> product_key",
        "customer_id -> customer_key",
        "latitude (dropped)",
        "longitude (dropped)",
    ],
    "customers": [
        "customer_id -> customer_key",
        "document_number",
        "document_type",
        "first_name",
        "last_name",
        "date_of_birth",
        "gender",
        "email",
        "mobile_phone",
        "landline_phone",
        "address",
        "city",
        "state",
        "postal_code",
    ],
    "products": [
        "product_id -> product_key",
        "customer_id -> customer_key",
        "product_number (dropped)",
    ],
    "bronze_meta": ["_source_file: absolute local path -> path relative to raw/"],
}

PII_COLS = {
    "customer_id",
    "product_id",
    "transaction_id",
    "first_name",
    "last_name",
    "document_number",
    "document_type",
    "email",
    "mobile_phone",
    "landline_phone",
    "phone",
    "address",
    "postal_code",
    "date_of_birth",
    "gender",
    "ip_address",
    "latitude",
    "longitude",
    "product_number",
    "state",
    "city",
}


def scan_masked_parquet(con, path):
    """Hard gate before upload: no PII column names, no raw ids / emails / phone numbers / known document numbers, names,
    phones or product numbers in any string value, and every *_key matches the salted-key format. Raises AssertionError."""
    rel = f"read_parquet('{path}')"
    cols = [(r[0], r[1]) for r in con.execute(f"DESCRIBE SELECT * FROM {rel}").fetchall()]
    bad = {c for c, _ in cols} & PII_COLS
    assert not bad, (path, "PII columns", bad)
    for c, ty in cols:
        if c.endswith("_key"):
            prefix = {"customer_key": "CUS", "product_key": "PRD", "transaction_key": "TXN"}[c]
            n = con.execute(
                f"SELECT count(*) FROM {rel} WHERE NOT regexp_full_match(\"{c}\", '{prefix}_[0-9a-f]{{20}}')"
            ).fetchone()[0]
            assert n == 0, (path, c, "bad key format", n)
        if ty != "VARCHAR" or c == "log_json":
            continue
        n = con.execute(f"""SELECT count(*) FROM {rel} WHERE regexp_matches("{c}", '(CLI|PRD|TRX)-[A-Z0-9]{{8,}}')
            OR regexp_matches("{c}", '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[a-z]{{2,}}')
            OR regexp_matches("{c}", '\\+[0-9]{{1,3}}[ -]?[0-9]{{1,4}}[ -][0-9]{{3}}')
            OR regexp_matches("{c}", '^/|/workspace/')
            OR "{c}" IN (SELECT document_number FROM silver.customers WHERE document_number IS NOT NULL)
            OR "{c}" IN (SELECT mobile_phone FROM silver.customers WHERE mobile_phone IS NOT NULL)
            OR "{c}" IN (SELECT landline_phone FROM silver.customers WHERE landline_phone IS NOT NULL)
            OR "{c}" IN (SELECT address FROM silver.customers WHERE address IS NOT NULL)
            OR "{c}" IN (SELECT first_name || ' ' || last_name FROM silver.customers)
            OR "{c}" IN (SELECT last_name FROM silver.customers WHERE last_name IS NOT NULL)
            OR "{c}" IN (SELECT product_number FROM silver.products WHERE product_number IS NOT NULL)""").fetchone()[
            0
        ]
        assert n == 0, (path, c, "PII-like values", n)
    return [c for c, _ in cols]


def run_layers(layers=("bronze", "silver")):
    """Export masked bronze/silver Parquet to out/<layer>/ and PII-scan every file. Returns {(layer, table): (path, local_count)}."""
    from common import salt

    con = connect(read_only=True)
    P = {"salt": salt()}
    con.execute("SET enable_progress_bar=false")
    files = {}
    for layer in layers:
        d = os.path.join(OUT, layer)
        os.makedirs(d, exist_ok=True)
        for name, q in _layer_sql(layer).items():
            p = os.path.join(d, f"{name}.parquet")
            con.execute(
                f"COPY ({q}) TO '{p}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 500000)",
                P if "$salt" in q else None,
            )
            n_src = con.execute(f"SELECT count(*) FROM {layer}.{LAYER_SOURCE[name]}").fetchone()[0]
            n_out = con.execute(f"SELECT count(*) FROM read_parquet('{p}')").fetchone()[0]
            assert n_src == n_out, (layer, name, n_src, n_out)
            cols = scan_masked_parquet(con, p)
            if (
                "customer_key" in cols
            ):  # masked keys must be the same salted keys as gold (joinable across layers)
                miss = con.execute(
                    f"SELECT count(*) FROM read_parquet('{p}') WHERE customer_key NOT IN (SELECT customer_key FROM gold.customers_masked)"
                ).fetchone()[0]
                assert miss == 0, (layer, name, "customer_key not in gold", miss)
            files[(layer, name)] = (p, n_out)
            print(
                f"{layer}.{name}: {n_out:,} rows, {round(os.path.getsize(p) / 1e6, 1)} MB, PII scan PASS, cols={cols}"
            )
    con.close()
    return files
