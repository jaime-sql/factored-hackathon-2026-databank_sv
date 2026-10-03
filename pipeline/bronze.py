# ruff: noqa: E501
"""BRONZE: raw CSVs exactly as delivered (all columns VARCHAR, no parsing), plus source filename and load timestamp."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import RAW, connect

SOURCES = {
    "transactions": "transactions/year=*/month=*/day=*/*.csv",
    "customers": "customers.csv",
    "products": "products.csv",
}


def run():
    con = connect()
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    for t, pat in SOURCES.items():
        path = os.path.join(RAW, pat)
        con.execute(f"""CREATE OR REPLACE TABLE bronze.{t} AS
            SELECT *, current_timestamp AS _loaded_at FROM read_csv('{path}', all_varchar=true, header=true,
                union_by_name=true, hive_partitioning=false, filename='_source_file')""")
        n = con.execute(f"SELECT count(*) FROM bronze.{t}").fetchone()[0]
        print(f"bronze.{t}: {n:,} rows")
    con.close()


if __name__ == "__main__":
    run()
