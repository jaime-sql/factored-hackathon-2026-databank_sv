# ruff: noqa: E501
#!/usr/bin/env python3
"""Live data-trust checks for the hackathon app -> static/data/trust.json: a JSON array, one object per check,
each exactly {label_es, label_pt, value, ok, checked_at} (System health strip on the Métricas page). Full detail -> stderr.

Connection strings come ONLY from environment variables (never hardcoded, never written to the output):
  SUPABASE_DB_URL  owner connection (counts, RLS, privilege catalog)
  APP_DB_URL       app_rw connection (eval-isolation probe)
Run:  uv run -q --with 'psycopg[binary]' python pipeline/trust_check.py [--out PATH]
Expected counts come from the local pipeline output (app_slice.sqlite) when present, otherwise from the
reconciled constants below (the same numbers load_supabase.py verified against the pipeline outputs).
"""

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys

import psycopg

TARGET_REF = "dmqwgbtrrnxkgcahunrc"
FORBIDDEN_REFS = ("kwbhytabavegnqfeidjw",)  # iglesiaSJB
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED_CONST = {
    "public.customers": 1091,
    "public.transactions": 40322,
    "eval.transaction_labels": 40322,
    "public.fraud_features": 38910,
    "public.synthetic_duplicates": 600,
    "public.meta": 4,
}
AUDIT_TABLES = ["app.audit_case", "app.audit_event", "app.audit_llm_call"]
AUDIT_VIEWS = ["app.audit_current", "app.audit_live", "app.audit_llm_call_current"]
PRIVS = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"]
WRITE_PRIVS = ["INSERT", "UPDATE", "DELETE", "TRUNCATE"]


def env_url(name):
    url = os.environ.get(name)
    if not url:
        raise SystemExit(f"{name} not set")
    if any(r in url for r in FORBIDDEN_REFS) or TARGET_REF not in url:
        raise SystemExit(f"{name} does not point at project {TARGET_REF}; refusing")
    return url


def expected_counts():
    p = os.path.join(ROOT, "app_slice.sqlite")
    if not os.path.exists(p):
        return dict(EXPECTED_CONST), "reconciled constants"
    s = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    one = lambda q: s.execute(q).fetchone()[0]  # noqa: E731
    exp = {
        "public.customers": one("SELECT count(*) FROM customers"),
        "public.transactions": one("SELECT count(*) FROM transactions"),
        "eval.transaction_labels": one(
            "SELECT count(*) FROM transactions WHERE is_fraud IS NOT NULL"
        ),
        "public.fraud_features": one(
            "SELECT count(*) FROM transactions WHERE transaction_status NOT IN ('Pending','Reversed')"
        ),
        "public.synthetic_duplicates": one("SELECT count(*) FROM synthetic_duplicates"),
        "public.meta": one("SELECT count(*) FROM meta"),
    }
    s.close()
    if exp != EXPECTED_CONST:
        raise SystemExit(f"pipeline output disagrees with reconciled constants: {exp}")
    return exp, "pipeline output (app_slice.sqlite)"


def reproducible_check():
    """Pass only if the one-command runner AND its pinned requirements exist. If the run marker out/last_run.json
    (written by run_all.sh after every step incl. tests succeeded) exists, it must also be consistent: built with the
    current requirements.txt and with app_slice counts equal to the current app_slice.sqlite."""
    import hashlib

    cmd = "bash pipeline/run_all.sh"
    runner = os.path.join(ROOT, "pipeline", "run_all.sh")
    req = os.path.join(ROOT, "pipeline", "requirements.txt")
    marker = os.path.join(ROOT, "out", "last_run.json")
    d = {
        "run_all_sh": os.path.isfile(runner),
        "requirements_txt": os.path.isfile(req),
        "last_run": None,
    }
    ok = d["run_all_sh"] and d["requirements_txt"]
    if ok and os.path.isfile(marker):
        try:
            m = json.load(open(marker))
            req_ok = (
                m.get("requirements_sha256") == hashlib.sha256(open(req, "rb").read()).hexdigest()
            )
            counts_ok = True
            sp = os.path.join(ROOT, "app_slice.sqlite")
            if os.path.exists(sp):
                s = sqlite3.connect(f"file:{sp}?mode=ro", uri=True)
                cur = {
                    t: s.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
                    for (t,) in s.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                }
                counts_ok = cur == m.get("app_slice_counts")
            d["last_run"] = {
                "finished_at": m.get("finished_at"),
                "duration_s": m.get("duration_s"),
                "requirements_match": req_ok,
                "app_slice_counts_match": counts_ok,
            }
            ok = req_ok and counts_ok
        except Exception as e:
            d["last_run"] = {"error": f"unreadable marker: {type(e).__name__}"}
            ok = False
    value = cmd
    if ok and d["last_run"] and d["last_run"].get("finished_at"):
        value = f"{cmd} · {d['last_run']['finished_at']}"  # language-neutral: command + last successful full run (UTC)
    return {"id": "reproducible", "pass": ok, "command": cmd, "value": value, "detail": d}


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "static", "data", "trust.json"))
    a = ap.parse_args()
    checks = []
    exp, exp_src = expected_counts()
    with (
        psycopg.connect(env_url("SUPABASE_DB_URL"), autocommit=True) as own,
        psycopg.connect(env_url("APP_DB_URL"), autocommit=True) as app,
    ):
        oc, ac = own.cursor(), app.cursor()
        ac.execute("SELECT current_user")
        app_role = ac.fetchone()[0]
        # 1 row counts
        det = {}
        for t, e in exp.items():
            oc.execute(f"SELECT count(*) FROM {t}")
            n = oc.fetchone()[0]
            det[t.split(".")[1]] = {"expected": e, "actual": n, "match": n == e}
        checks.append(
            {
                "id": "row_counts",
                "pass": all(v["match"] for v in det.values()),
                "detail": {
                    "tables_matching": f"{sum(v['match'] for v in det.values())}/{len(det)}",
                    "tables": det,
                },
            }
        )
        # 2 eval isolation (probe as app_rw)
        try:
            ac.execute("SELECT 1 FROM eval.transaction_labels LIMIT 1")
            rows = len(ac.fetchall())
            iso = {"pass": rows == 0, "detail": {"result": f"{rows} rows visible"}}
        except psycopg.errors.InsufficientPrivilege:
            iso = {"pass": True, "detail": {"result": "permission denied"}}
        checks.append({"id": "eval_isolated", **iso, "detail": {**iso["detail"], "role": app_role}})
        # 3 RLS
        oc.execute("""SELECT n.nspname, c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                      WHERE n.nspname IN ('public','eval','app') AND c.relkind IN ('r','p') ORDER BY 1,2""")
        rls = oc.fetchall()
        off = [f"{s}.{t}" for s, t, r in rls if not r]
        checks.append(
            {
                "id": "rls",
                "pass": bool(rls) and not off,
                "detail": {
                    "enabled": f"{len(rls) - len(off)}/{len(rls)}",
                    "tables_without_rls": off,
                },
            }
        )

        # 4 audit append-only
        def privs(obj):
            oc.execute("SELECT to_regclass(%s) IS NOT NULL", [obj])
            if not oc.fetchone()[0]:
                return None
            got = []
            for p in PRIVS:
                oc.execute("SELECT has_table_privilege(%s, %s, %s)", [app_role, obj, p])
                if oc.fetchone()[0]:
                    got.append(p)
            return got

        audit = {}
        ok = True
        for o in AUDIT_TABLES:
            g = privs(o)
            audit[o] = g if g is not None else "missing"
            ok &= g is not None and sorted(g) == ["INSERT", "SELECT"]
        for o in AUDIT_VIEWS:
            g = privs(o)
            audit[o] = g if g is not None else "missing"
            ok &= g is not None and g == ["SELECT"]
        oc.execute("""SELECT n.nspname||'.'||c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                      WHERE n.nspname='app' AND c.relname LIKE 'audit%%' AND c.relkind IN ('r','p','v','m')""")
        extra_bad = []
        for (o,) in oc.fetchall():
            g = privs(o) or []
            if set(g) & {"UPDATE", "DELETE", "TRUNCATE"}:
                extra_bad.append(o)
        ok &= not extra_bad
        checks.append(
            {
                "id": "audit_append_only",
                "pass": ok,
                "detail": {
                    "role": app_role,
                    "privileges": audit,
                    "audit_objects_with_update_delete_truncate": extra_bad,
                },
            }
        )
        # 5 app_rw read-only on public
        oc.execute("""SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                      WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m') ORDER BY 1""")
        writable = []
        pub = [r[0] for r in oc.fetchall()]
        for t in pub:
            for p in WRITE_PRIVS:
                oc.execute("SELECT has_table_privilege(%s, %s, %s)", [app_role, f"public.{t}", p])
                if oc.fetchone()[0]:
                    writable.append(f"{t}:{p}")
        checks.append(
            {
                "id": "app_rw_read_only_public",
                "pass": not writable,
                "detail": {
                    "role": app_role,
                    "public_objects_checked": len(pub),
                    "write_grants": writable,
                },
            }
        )
    # 6 reproducible
    checks.append(reproducible_check())
    all_pass = all(c["pass"] for c in checks)
    ts = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    by = {c["id"]: c for c in checks}
    ok_txt = lambda c: "OK" if c["pass"] else "FAIL"  # noqa: E731
    LABELS = {  # id -> (label_es, label_pt, value)
        "row_counts": (
            "Tablas que cuadran con la fuente del pipeline",
            "Tabelas que batem com a fonte do pipeline",
            by["row_counts"]["detail"]["tables_matching"],
        ),
        "eval_isolated": (
            "Etiquetas de evaluación aisladas de la app",
            "Rótulos de avaliação isolados do app",
            ok_txt(by["eval_isolated"]),
        ),
        "rls": (
            "Seguridad por fila (RLS) activa en todas las tablas",
            "Segurança por linha (RLS) ativa em todas as tabelas",
            by["rls"]["detail"]["enabled"],
        ),
        "audit_append_only": (
            "Auditoría solo admite inserciones",
            "Auditoria aceita somente inserções",
            ok_txt(by["audit_append_only"]),
        ),
        "app_rw_read_only_public": (
            "La app solo lee los datos públicos",
            "O app só lê os dados públicos",
            ok_txt(by["app_rw_read_only_public"]),
        ),
        "reproducible": (
            "Reproducible con un comando",
            "Reproduzível com um comando",
            by["reproducible"]["value"],
        ),
    }
    out = [
        {
            "label_es": LABELS[c["id"]][0],
            "label_pt": LABELS[c["id"]][1],
            "value": LABELS[c["id"]][2],
            "ok": bool(c["pass"]),
            "checked_at": ts,
        }
        for c in checks
    ]
    # full diagnostic detail goes to stderr only (not into the display file)
    print(
        json.dumps(
            {"checked_at": ts, "all_pass": all_pass, "expected_source": exp_src, "checks": checks},
            ensure_ascii=False,
            indent=1,
        ),
        file=sys.stderr,
    )
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(run())
