#!/usr/bin/env bash
# Full pipeline: bronze -> silver -> gold -> fixture/app slice -> tests -> (optional) Databricks load (masked gold + masked bronze/silver).
# Usage: bash pipeline/run_all.sh [--databricks]   (needs ./.env with PSEUDO_SALT; DATABRICKS_TOKEN in env for --databricks)
# Python env comes from pipeline/requirements.txt: via `uv run` (Python 3.12) if uv is installed, else a .venv built with python3 -m venv.
set -euo pipefail
cd "$(dirname "$0")/.."
REQ=pipeline/requirements.txt
if command -v uv >/dev/null 2>&1; then
  PY="uv run --no-project --python 3.12 --with-requirements $REQ python"
else
  if [[ ! -x .venv/bin/python ]]; then python3 -m venv .venv; fi
  .venv/bin/python -m pip install -q -r "$REQ"
  PY=.venv/bin/python
fi
START_EPOCH=$(date +%s)
$PY pipeline/bronze.py
$PY pipeline/silver.py
$PY pipeline/gold.py
$PY pipeline/app_outputs.py
$PY pipeline/tests/test_leakage.py
$PY pipeline/tests/test_isolation.py
$PY pipeline/export.py
$PY pipeline/tests/test_pii.py
if [[ "${1:-}" == "--databricks" ]]; then $PY pipeline/databricks_load.py; fi
# Marker of the last successful full run (only reached if every step above succeeded, thanks to set -e).
mkdir -p out
$PY - "$START_EPOCH" "${1:-}" <<'PYEOF'
import sys, json, sqlite3, hashlib, datetime as dt, platform
start = int(sys.argv[1]); now = dt.datetime.now(dt.timezone.utc)
db = sqlite3.connect("app_slice.sqlite")
counts = {t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
          for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
manifest = json.load(open("splits_manifest.json"))
json.dump({"finished_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
           "duration_s": int(now.timestamp()) - start,
           "databricks": sys.argv[2] == "--databricks",
           "python": platform.python_version(),
           "requirements_sha256": hashlib.sha256(open("pipeline/requirements.txt", "rb").read()).hexdigest(),
           "app_slice_counts": counts,
           "splits_manifest_sha256": hashlib.sha256(open("splits_manifest.json", "rb").read()).hexdigest(),
           "tests": ["test_leakage", "test_isolation", "test_pii"]},
          open("out/last_run.json", "w"), indent=2)
print("wrote out/last_run.json")
PYEOF
