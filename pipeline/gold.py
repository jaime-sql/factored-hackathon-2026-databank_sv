# ruff: noqa: E501
"""GOLD: masked, customer-isolated transactions + fraud-triage modeling table with time-based split and manifest."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import OUT, SEED, TS_OFFSET_HOURS, connect, pseudo_sql, salt, sha256_ids

# Columns allowed in gold.transactions_masked (explicit allow-list; everything else is dropped)
MASKED_COLUMNS = [
    "transaction_key",
    "customer_key",
    "product_key",
    "product_type",
    "transaction_ts_utc",
    "transaction_ts_local",
    "process_date",
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
    "customer_country",
    "customer_segment",
    "customer_accent",
]
DROPPED_PII = [
    "customer_id (->customer_key)",
    "product_id (->product_key)",
    "transaction_id (->transaction_key)",
    "latitude",
    "longitude",
    "customers.first_name/last_name/document_number/document_type/date_of_birth/gender/email/mobile_phone/landline_phone/address/postal_code/city/state",
    "products.product_number",
]

# Fraud-triage model: features known at authorization time only
FEATURES_NUMERIC = [
    "amount",
    "log_amount",
    "amount_usd",
    "fraud_score",
    "local_hour",
    "local_dow",
    "is_night",
    "is_weekend",
    "is_cross_border",
    "customer_tenure_days",
    "product_tenure_days",
    "prior_tx_count",
    "prior_tx_count_1h",
    "prior_tx_count_24h",
    "prior_tx_count_7d",
    "secs_since_prev_tx",
    "prior_mean_amount_same_ccy",
    "amount_to_prior_mean",
    "prior_count_same_merchant",
    "prior_cross_border_count_30d",
]
FEATURES_CATEGORICAL = [
    "currency",
    "channel",
    "transaction_type",
    "transaction_category",
    "merchant_category",
    "merchant_name",
    "transaction_country",
    "transaction_city",
    "product_type",
]
LABEL = "is_fraud"
BASELINE = "baseline_flag"  # fraud_score >= 30 (null score -> False)
SLICE_COLUMNS = [
    "customer_country",
    "customer_segment",
    "customer_accent",
]  # for fairness evaluation, not model features
ID_COLUMNS = ["transaction_key", "customer_key", "transaction_ts_utc", "split"]
EXCLUDED = [
    "transaction_status",
    "response_code",
    "is_fraud (label only)",
    "latitude",
    "longitude",
    "products.current_balance",
    "products.product_status",
    "products.last_transaction_date",
    "products.days_past_due",
    "products.last_updated",
    "products.credit_limit",
    "products.has_linked_app",
    "customers.credit_score",
    "customers.estimated_monthly_income",
    "customers.customer_status",
    "customers.last_updated",
    "any complaint / interaction / survey join",
    "any aggregate over prior labels (is_fraud) or prior statuses",
    "any aggregate including same-or-later timestamps",
]
FORBIDDEN_IN_MODEL = [
    "transaction_status",
    "response_code",
    "latitude",
    "longitude",
    "current_balance",
    "product_status",
    "last_transaction_date",
    "days_past_due",
    "credit_score",
    "estimated_monthly_income",
    "customer_status",
    "complaint_id",
    "compensation_granted",
    "resolution",
    "status",
]
SPLIT_FRACTIONS = (0.70, 0.85)
ML_SCOPE = "transaction_status NOT IN ('Pending','Reversed')   -- Pending/Reversed are handled by deterministic rules"


def run():
    con = connect()
    s = salt()
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    P = {"salt": s}
    con.execute(
        f"""CREATE OR REPLACE TABLE gold.customers_masked AS
        SELECT {pseudo_sql("customer_id", "customer")} AS customer_key, country AS customer_country, segment AS customer_segment,
               coalesce(detected_accent, 'unknown') AS customer_accent, CAST(registration_date AS DATE) AS registration_date
        FROM silver.customers""",
        P,
    )
    con.execute(
        f"""CREATE OR REPLACE TABLE gold.transactions_masked AS
        SELECT {pseudo_sql("t.transaction_id", "transaction")} AS transaction_key,
               {pseudo_sql("t.customer_id", "customer")} AS customer_key,
               {pseudo_sql("t.product_id", "product")} AS product_key,
               p.product_type, t.transaction_ts_utc, t.transaction_ts_local, t.process_date, t.transaction_type, t.transaction_category,
               t.amount, t.currency, t.amount_usd, t.channel, t.branch_id, t.merchant_name, t.merchant_category,
               t.transaction_country, t.transaction_city, t.transaction_status, t.response_code, t.is_fraud, t.fraud_score,
               c.country AS customer_country, c.segment AS customer_segment, coalesce(c.detected_accent, 'unknown') AS customer_accent
        FROM silver.transactions t
        LEFT JOIN silver.products p USING (product_id)
        LEFT JOIN silver.customers c ON c.customer_id = t.customer_id""",
        P,
    )
    got = [r[0] for r in con.execute("DESCRIBE gold.transactions_masked").fetchall()]
    assert got == MASKED_COLUMNS, got
    # ---- fraud features (history over ALL transactions, strictly earlier timestamps only)
    con.execute("""CREATE OR REPLACE TEMP TABLE hist AS
        SELECT t.transaction_key,
          count(*) OVER w_all AS prior_tx_count,
          count(*) OVER w_1h AS prior_tx_count_1h,
          count(*) OVER w_24h AS prior_tx_count_24h,
          count(*) OVER w_7d AS prior_tx_count_7d,
          date_diff('second', max(t.transaction_ts_utc) OVER w_all, t.transaction_ts_utc) AS secs_since_prev_tx,
          sum(CASE WHEN t.transaction_country <> t.customer_country THEN 1 ELSE 0 END) OVER w_30d AS prior_cross_border_count_30d
        FROM gold.transactions_masked t
        WINDOW w_all AS (PARTITION BY customer_key ORDER BY transaction_ts_utc RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL 1 SECOND PRECEDING),
               w_1h  AS (PARTITION BY customer_key ORDER BY transaction_ts_utc RANGE BETWEEN INTERVAL 1 HOUR PRECEDING AND INTERVAL 1 SECOND PRECEDING),
               w_24h AS (PARTITION BY customer_key ORDER BY transaction_ts_utc RANGE BETWEEN INTERVAL 24 HOUR PRECEDING AND INTERVAL 1 SECOND PRECEDING),
               w_7d  AS (PARTITION BY customer_key ORDER BY transaction_ts_utc RANGE BETWEEN INTERVAL 7 DAY PRECEDING AND INTERVAL 1 SECOND PRECEDING),
               w_30d AS (PARTITION BY customer_key ORDER BY transaction_ts_utc RANGE BETWEEN INTERVAL 30 DAY PRECEDING AND INTERVAL 1 SECOND PRECEDING)""")
    con.execute("""CREATE OR REPLACE TEMP TABLE hist_ccy AS
        SELECT transaction_key, avg(amount) OVER w AS prior_mean_amount_same_ccy
        FROM gold.transactions_masked
        WINDOW w AS (PARTITION BY customer_key, currency ORDER BY transaction_ts_utc RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL 1 SECOND PRECEDING)""")
    con.execute("""CREATE OR REPLACE TEMP TABLE hist_mer AS
        SELECT transaction_key, count(*) OVER w AS prior_count_same_merchant
        FROM gold.transactions_masked WHERE merchant_name IS NOT NULL
        WINDOW w AS (PARTITION BY customer_key, merchant_name ORDER BY transaction_ts_utc RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL 1 SECOND PRECEDING)""")
    con.execute(
        """CREATE OR REPLACE TEMP TABLE prod AS
        SELECT pk AS product_key, opening_date FROM (SELECT """
        + pseudo_sql("product_id", "product")
        + """ AS pk, opening_date FROM silver.products)""",
        P,
    )
    con.execute(f"""CREATE OR REPLACE TEMP TABLE feat AS
        SELECT t.transaction_key, t.customer_key, t.transaction_ts_utc,
          t.amount, ln(1 + greatest(t.amount, 0)) AS log_amount, t.amount_usd, t.fraud_score,
          hour(t.transaction_ts_local) AS local_hour, isodow(t.transaction_ts_local) AS local_dow,
          CAST(hour(t.transaction_ts_local) < 6 AS INTEGER) AS is_night, CAST(isodow(t.transaction_ts_local) >= 6 AS INTEGER) AS is_weekend,
          CAST(t.transaction_country <> t.customer_country AS INTEGER) AS is_cross_border,
          date_diff('day', c.registration_date, CAST(t.transaction_ts_local AS DATE)) AS customer_tenure_days,
          date_diff('day', pr.opening_date, CAST(t.transaction_ts_local AS DATE)) AS product_tenure_days,
          h.prior_tx_count, h.prior_tx_count_1h, h.prior_tx_count_24h, h.prior_tx_count_7d, h.secs_since_prev_tx,
          hc.prior_mean_amount_same_ccy, t.amount / nullif(hc.prior_mean_amount_same_ccy, 0) AS amount_to_prior_mean,
          coalesce(hm.prior_count_same_merchant, 0) AS prior_count_same_merchant, h.prior_cross_border_count_30d,
          t.currency, t.channel, t.transaction_type, t.transaction_category, t.merchant_category, t.merchant_name,
          t.transaction_country, t.transaction_city, t.product_type,
          t.is_fraud, coalesce(t.fraud_score >= 30, false) AS baseline_flag,
          t.customer_country, t.customer_segment, t.customer_accent
        FROM gold.transactions_masked t
        JOIN hist h USING (transaction_key) JOIN hist_ccy hc USING (transaction_key)
        LEFT JOIN hist_mer hm USING (transaction_key)
        LEFT JOIN gold.customers_masked c USING (customer_key)
        LEFT JOIN prod pr USING (product_key)
        WHERE t.{ML_SCOPE.split("--")[0].strip()}""")
    c1, c2 = con.execute(
        f"SELECT quantile_disc(transaction_ts_utc, {SPLIT_FRACTIONS[0]}), quantile_disc(transaction_ts_utc, {SPLIT_FRACTIONS[1]}) FROM feat"
    ).fetchone()
    cols = (
        ["transaction_key", "customer_key", "transaction_ts_utc"]
        + FEATURES_NUMERIC
        + FEATURES_CATEGORICAL
        + [LABEL, BASELINE]
        + SLICE_COLUMNS
    )
    con.execute(f"""CREATE OR REPLACE TABLE gold.fraud_features AS
        SELECT {", ".join(cols)}, CASE WHEN transaction_ts_utc < TIMESTAMP '{c1}' THEN 'train'
                                      WHEN transaction_ts_utc < TIMESTAMP '{c2}' THEN 'val' ELSE 'test' END AS split
        FROM feat ORDER BY transaction_ts_utc, transaction_key""")
    manifest = {
        "seed": SEED,
        "split_rule": "train: ts_utc < cutoff_train_end; val: cutoff_train_end <= ts_utc < cutoff_val_end; test: ts_utc >= cutoff_val_end",
        "time_column": "transaction_ts_utc (raw transaction_date; local = utc - %dh)"  # noqa: UP031
        % TS_OFFSET_HOURS,
        "cutoff_train_end": str(c1),
        "cutoff_val_end": str(c2),
        "ml_scope": ML_SCOPE,
        "label": LABEL,
        "baseline": "baseline_flag = coalesce(fraud_score >= 30, false)",
        "features_numeric": FEATURES_NUMERIC,
        "features_categorical": FEATURES_CATEGORICAL,
        "slice_columns_not_features": SLICE_COLUMNS,
        "excluded": EXCLUDED,
        "hash": "sha256 over sorted transaction_key joined by \\n (trailing \\n)",
        "splits": {},
    }
    for sp in ("train", "val", "test"):
        ids = [
            r[0]
            for r in con.execute(
                "SELECT transaction_key FROM gold.fraud_features WHERE split=?", [sp]
            ).fetchall()
        ]
        n, pos, lo, hi, bpos, tp = con.execute(
            """SELECT count(*), count(*) FILTER (WHERE is_fraud), min(transaction_ts_utc), max(transaction_ts_utc),
            count(*) FILTER (WHERE baseline_flag), count(*) FILTER (WHERE baseline_flag AND is_fraud) FROM gold.fraud_features WHERE split=?""",
            [sp],
        ).fetchone()
        manifest["splits"][sp] = {
            "rows": n,
            "positives": pos,
            "positive_rate": round(pos / n, 6) if n else None,
            "min_ts": str(lo),
            "max_ts": str(hi),
            "baseline_flagged": bpos,
            "baseline_true_positives": tp,
            "sha256_sorted_ids": sha256_ids(ids),
        }
    os.makedirs(OUT, exist_ok=True)
    json.dump(
        manifest,
        open(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "splits_manifest.json"
            ),
            "w",
        ),
        indent=2,
    )
    for t in ("transactions_masked", "customers_masked", "fraud_features"):
        n = con.execute(f"SELECT count(*) FROM gold.{t}").fetchone()[0]
        print(f"gold.{t}: {n:,}")
    print(json.dumps(manifest["splits"], indent=1))
    print("cutoffs", c1, c2)
    con.close()


if __name__ == "__main__":
    run()
