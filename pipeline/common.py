# ruff: noqa: E501
"""Shared config for the dispute-intake data pipeline. Secrets come only from env / ../.env and are never printed."""

import hashlib
import os
import re

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # /workspace/hackathon-data
RAW = os.path.join(ROOT, "raw")  # local copy of s3://.../data/
DB = os.environ.get("PIPELINE_DB", os.path.join(ROOT, "cache", "pipeline.duckdb"))
OUT = os.path.join(ROOT, "out")  # parquet exports (gitignored)
FIXTURES = os.path.join(ROOT, "fixtures")
SLICE = os.path.join(ROOT, "app_slice.sqlite")
SEED = 20260929
TS_OFFSET_HOURS = 6  # transaction_date is process_date-local + 6h: measured offset range [6h, 30h) -> UTC stamps vs UTC-6 local day


def load_env():
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)


def salt():
    load_env()
    s = os.environ.get("PSEUDO_SALT")
    if not s or len(s) < 32:
        raise SystemExit("PSEUDO_SALT missing/short in .env")
    return s


def connect(read_only=False):
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = duckdb.connect(DB, read_only=read_only)
    con.execute("SET memory_limit='7GB'; SET preserve_insertion_order=false")
    return con


CUSTOMER_KEY_RE = re.compile(r"^CUS_[0-9a-f]{20}$")


def pseudo_sql(expr, kind, salt_param="$salt"):
    """SQL expression producing a salted pseudonymous id. kind prefixes the hash input so ids are not linkable across kinds."""
    prefix = {"customer": "CUS_", "product": "PRD_", "transaction": "TXN_"}[kind]
    return f"'{prefix}' || left(sha256({salt_param} || ':{kind}:' || {expr}), 20)"


def sha256_ids(ids):
    h = hashlib.sha256()
    for i in sorted(ids):
        h.update(i.encode())
        h.update(b"\n")
    return h.hexdigest()
