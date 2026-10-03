# ruff: noqa: E501
"""Load masked gold Parquet into Databricks Unity Catalog: Files API -> volume, then Delta tables via SQL Statement Execution API.
Requires DATABRICKS_TOKEN in env (never printed). Bronze/silver are loaded ONLY as masked copies (export.run_layers: allow-listed
columns, salted keys, direct PII dropped, PII scan must pass) into {cat}.bronze.*_masked / {cat}.silver.*_masked via per-schema
volumes; the unmasked bronze/silver tables never leave the local DuckDB.
Usage: python pipeline/databricks_load.py                # gold + masked bronze/silver
       python pipeline/databricks_load.py --layers-only  # masked bronze/silver only (gold untouched)"""

import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(__file__))
import export
from common import ROOT

HOST = os.environ.get("DATABRICKS_HOST", "https://dbc-6b5953ee-73b5.cloud.databricks.com")
TOKEN = os.environ.get("DATABRICKS_TOKEN")
if not TOKEN:
    raise SystemExit("DATABRICKS_TOKEN not set in env; refusing to continue")
H = {"Authorization": f"Bearer {TOKEN}"}
WAREHOUSE_NAME = "Serverless Starter Warehouse"
S = requests.Session()
S.headers.update(H)


def api(method, path, **kw):
    r = S.request(method, HOST + path, timeout=600, **kw)
    if r.status_code >= 300:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:400]}")
    return r.json() if r.text else {}


def warehouse():
    whs = api("GET", "/api/2.0/sql/warehouses")["warehouses"]
    wh = next(w for w in whs if w["name"] == WAREHOUSE_NAME)
    if wh["state"] not in ("RUNNING", "STARTING"):
        api("POST", f"/api/2.0/sql/warehouses/{wh['id']}/start")
    for _ in range(120):
        st = api("GET", f"/api/2.0/sql/warehouses/{wh['id']}")["state"]
        if st == "RUNNING":
            return wh["id"]
        time.sleep(5)
    raise RuntimeError("warehouse did not start")


def sql(wid, stmt):
    r = api(
        "POST",
        "/api/2.0/sql/statements",
        json={
            "warehouse_id": wid,
            "statement": stmt,
            "wait_timeout": "50s",
            "on_wait_timeout": "CONTINUE",
        },
    )
    while r["status"]["state"] in ("PENDING", "RUNNING"):
        time.sleep(3)
        r = api("GET", f"/api/2.0/sql/statements/{r['statement_id']}")
    if r["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(f"SQL failed: {stmt[:120]} -> {r['status']}")
    return r.get("result", {}).get("data_array")


def catalog():
    cats = [c["name"] for c in api("GET", "/api/2.1/unity-catalog/catalogs").get("catalogs", [])]
    return (
        "workspace"
        if "workspace" in cats
        else next(c for c in cats if c not in ("system", "samples"))
    )


def upload(local, remote):
    with open(local, "rb") as f:
        r = S.put(
            HOST + "/api/2.0/fs/files" + remote,
            params={"overwrite": "true"},
            data=f,
            timeout=1800,
            headers={"Content-Type": "application/octet-stream"},
        )
    if r.status_code >= 300:
        raise RuntimeError(f"upload {remote} -> {r.status_code}: {r.text[:300]}")


def run():
    files = export.run()
    wid = warehouse()
    cat = catalog()
    for sch in ("bronze", "silver", "gold"):
        sql(
            wid,
            f"CREATE SCHEMA IF NOT EXISTS {cat}.{sch} COMMENT 'dispute-intake pipeline ({sch})'",
        )
    sql(
        wid,
        f"CREATE VOLUME IF NOT EXISTS {cat}.gold.landing COMMENT 'masked parquet drops for gold tables'",
    )
    results = {}
    for name, local in files.items():
        remote = f"/Volumes/{cat}/gold/landing/{name}.parquet"
        t0 = time.time()
        upload(local, remote)
        sql(wid, f"CREATE OR REPLACE TABLE {cat}.gold.{name} AS SELECT * FROM parquet.`{remote}`")
        n = int(sql(wid, f"SELECT count(*) FROM {cat}.gold.{name}")[0][0])
        results[f"{cat}.gold.{name}"] = n
        print(f"{cat}.gold.{name}: {n:,} rows ({time.time() - t0:.0f}s)")
    json.dump(results, open(os.path.join(ROOT, "out", "databricks_load.json"), "w"), indent=1)
    return results


LAYER_COMMENTS = {
    "bronze": "MASKED copy of bronze (raw CSVs as delivered, all VARCHAR): salted CUS_/PRD_/TXN_ keys replace raw ids; names, document, "
    "DOB, gender, email, phones, address, postal code, city/state, product_number and lat/long dropped. Unmasked bronze stays local.",
    "silver": "MASKED copy of silver (contract-checked, typed, deduped): salted CUS_/PRD_/TXN_ keys replace raw ids; names, document, "
    "DOB, gender, email, phones, address, postal code, city/state, product_number and lat/long dropped. Unmasked silver stays local.",
}


def run_layers(wid=None, cat=None, layers=("bronze", "silver")):
    """Masked bronze/silver: export + PII scan locally (raises before any upload on failure), then one upload + CTAS + count per table."""
    files = export.run_layers(layers)  # AssertionError here = nothing uploaded
    wid = wid or warehouse()
    cat = cat or catalog()
    results = {}
    for layer in layers:
        sql(wid, f"CREATE SCHEMA IF NOT EXISTS {cat}.{layer}")
        sql(
            wid,
            f"CREATE VOLUME IF NOT EXISTS {cat}.{layer}.landing COMMENT 'masked parquet drops for {layer} tables'",
        )
    for (layer, name), (local, n_local) in files.items():
        remote = f"/Volumes/{cat}/{layer}/landing/{name}.parquet"
        t0 = time.time()
        upload(local, remote)
        sql(
            wid, f"CREATE OR REPLACE TABLE {cat}.{layer}.{name} AS SELECT * FROM parquet.`{remote}`"
        )
        n = int(sql(wid, f"SELECT count(*) FROM {cat}.{layer}.{name}")[0][0])
        results[f"{cat}.{layer}.{name}"] = {
            "databricks": n,
            "local": n_local,
            "match": n == n_local,
        }
        print(
            f"{cat}.{layer}.{name}: databricks {n:,} / local {n_local:,} ({time.time() - t0:.0f}s)"
        )
    for layer in layers:
        sql(wid, f"COMMENT ON SCHEMA {cat}.{layer} IS '{LAYER_COMMENTS[layer]}'")
    json.dump(
        results, open(os.path.join(ROOT, "out", "databricks_load_layers.json"), "w"), indent=1
    )
    bad = {k: v for k, v in results.items() if not v["match"]}
    if bad:
        raise RuntimeError(f"count mismatch: {bad}")
    return results


if __name__ == "__main__":
    if "--layers-only" in sys.argv:
        run_layers()
    else:
        run()
        run_layers()
