"""SQLite and Postgres operational store.

Audit rows are inserted, never updated. A correction is a new row whose
supersedes_audit_id points at the row it replaces. audit_current is the tip
of each chain and stays unfiltered for the eval runner. Desk KPIs read
audit_live. SQLite mirrors that rule in this process because it has no roles.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.ops.guard import assert_statement_allowed

logger = logging.getLogger(__name__)

_SCHEMA_WARNING = (
    "test-traffic schema is missing (is_test, test_cases, or audit_live); "
    "run migrations/002_is_test.sql as the database owner. "
    "Case inserts omit is_test, test marks are ignored, and metrics read audit_current."
)

_PRICES = (
    ("gpt-4o-mini", 0.15, 0.60, "2026-09-29", "https://openai.com/api/pricing/"),
    ("openai/gpt-4o-mini", 0.15, 0.60, "2026-09-29", "https://openrouter.ai/models"),
)
_ASSUMPTIONS = (
    ("wage_low_usd_per_hour", 6, "ASSUMPTION from cost projection"),
    ("wage_mid_usd_per_hour", 12, "ASSUMPTION from cost projection"),
    ("wage_high_usd_per_hour", 20, "ASSUMPTION from cost projection"),
    ("queja_handle_seconds", 434.6, "ASSUMPTION handle time"),
    ("disputes_per_month", 377.49, "historical average, projection only"),
)


def _now() -> datetime:
    return datetime.now(UTC)


def _flags_out(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            loaded = json.loads(text)
            return [str(item) for item in loaded]
        return [part for part in text.strip("{}").split(",") if part]
    return [str(value)]


class OpsStore:
    def __init__(self, backend: str, path: str = "", dsn: str = "") -> None:
        if backend not in {"sqlite", "postgres"}:
            raise ValueError("unknown backend")
        self.backend = backend
        self.path = path
        self.dsn = dsn
        self.readback_tamper: Any = None
        self.migrations_ok = True
        self._schema_warned = False
        if backend == "sqlite":
            self._init_sqlite()
        else:
            self._ensure_postgres_is_test()
            self._ensure_postgres_view_grants()
            self._ensure_postgres_judge()
        self.refresh_test_schema()

    def _q(self, sql: str) -> str:
        if self.backend == "postgres":
            return sql.replace("?", "%s")
        return sql

    def _table(self, name: str) -> str:
        if self.backend == "postgres":
            return f"app.{name}"
        return name

    def _params(self, params: tuple[object, ...]) -> tuple[object, ...]:
        if self.backend != "sqlite":
            return params
        adapted: list[object] = []
        for value in params:
            if isinstance(value, datetime):
                adapted.append(value.isoformat())
            else:
                adapted.append(value)
        return tuple(adapted)

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, Any]]:
        assert_statement_allowed(sql)
        params = self._params(params)
        query = self._q(sql)
        if self.backend == "sqlite":
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                if cursor.description is None:
                    return []
                return [dict(row) for row in cursor.fetchall()]
        from app.db import connect_app

        with connect_app(self.dsn) as conn:
            cursor = conn.execute(query, params)
            if cursor.description is None:
                conn.commit()
                return []
            rows = [dict(row) for row in cursor.fetchall()]
            conn.commit()
            return rows

    def _write(self, sql: str, params: tuple[object, ...]) -> int:
        assert_statement_allowed(sql)
        params = self._params(params)
        query = self._q(sql)
        if self.backend == "sqlite":
            with sqlite3.connect(self.path) as conn:
                cursor = conn.execute(query, params)
                return int(cursor.rowcount)
        from app.db import connect_app

        with connect_app(self.dsn) as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return int(cursor.rowcount)

    def refresh_test_schema(self) -> bool:
        """True when is_test, test_cases, and audit_live are all present."""
        try:
            present = self._probe_test_schema()
        except Exception:
            present = False
        if present:
            self.migrations_ok = True
            return True
        self._mark_migrations_missing()
        return False

    def _mark_migrations_missing(self) -> None:
        self.migrations_ok = False
        if self._schema_warned:
            return
        self._schema_warned = True
        logger.warning(_SCHEMA_WARNING)

    def _probe_test_schema(self) -> bool:
        if self.backend == "sqlite":
            with sqlite3.connect(self.path) as conn:
                return _sqlite_has_test_schema(conn)
        columns = self.execute(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'app' AND column_name = 'is_test' "
            "AND table_name IN ('cases', 'audit_case', 'audit_llm_call')"
        )
        found = {str(row["table_name"]) for row in columns}
        if found != {"cases", "audit_case", "audit_llm_call"}:
            return False
        tables = self.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'app' AND table_name = 'test_cases'"
        )
        views = self.execute(
            "SELECT table_name FROM information_schema.views "
            "WHERE table_schema = 'app' AND table_name = 'audit_live'"
        )
        return bool(tables and views)

    def _insert_with_optional_test(
        self,
        table: str,
        columns: str,
        params: tuple[object, ...],
        *,
        is_test: bool,
        extras: tuple[tuple[str, object], ...] = (),
    ) -> None:
        without = (
            f"INSERT INTO {self._table(table)} ({columns}) VALUES ({_placeholders(len(params))})"
        )
        if not self.migrations_ok:
            self._write(without, params)
            return
        optional = (("is_test", is_test),) + extras
        for count in range(len(optional), -1, -1):
            chosen = optional[:count]
            names = ", ".join(name for name, _value in chosen)
            values = params + tuple(value for _name, value in chosen)
            sql_columns = columns if not names else f"{columns}, {names}"
            try:
                self._write(
                    f"INSERT INTO {self._table(table)} ({sql_columns}) "
                    f"VALUES ({_placeholders(len(values))})",
                    values,
                )
                return
            except Exception as exc:
                if not _missing_added_column(exc):
                    raise
                if "is_test" in str(exc).lower():
                    self._mark_migrations_missing()
        self._write(without, params)

    def _init_sqlite(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cases (
                  case_id TEXT PRIMARY KEY,
                  customer_key TEXT NOT NULL,
                  transaction_key TEXT,
                  state TEXT NOT NULL,
                  language TEXT NOT NULL,
                  case_type TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  closed_at TEXT,
                  latest_audit_id TEXT,
                  is_eval_case INTEGER NOT NULL DEFAULT 0,
                  eval_run_id TEXT,
                  case_source TEXT,
                  is_test INTEGER NOT NULL DEFAULT 0,
                  demo_attack INTEGER NOT NULL DEFAULT 0,
                  reply_draft TEXT,
                  reply_sent TEXT
                );
                CREATE TABLE IF NOT EXISTS audit_case (
                  audit_id TEXT PRIMARY KEY,
                  case_id TEXT NOT NULL,
                  supersedes_audit_id TEXT,
                  recorded_at TEXT NOT NULL,
                  case_type TEXT NOT NULL,
                  customer_segment TEXT,
                  final_resolution_status TEXT,
                  case_created_at TEXT NOT NULL,
                  case_closed_at TEXT,
                  decision TEXT,
                  automation_attempted INTEGER NOT NULL,
                  handoff_reason TEXT,
                  handoff_packet_complete INTEGER,
                  language TEXT NOT NULL,
                  country TEXT,
                  accent_group TEXT,
                  rule_or_model_version TEXT,
                  prompt_version TEXT,
                  fraud_score REAL,
                  model_risk_score REAL,
                  guardrail_flags TEXT NOT NULL,
                  is_eval_case INTEGER NOT NULL DEFAULT 0,
                  eval_run_id TEXT,
                  case_source TEXT,
                  is_test INTEGER NOT NULL DEFAULT 0,
                  demo_attack INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS audit_llm_call (
                  audit_id TEXT PRIMARY KEY,
                  llm_call_id TEXT NOT NULL,
                  case_id TEXT NOT NULL,
                  supersedes_audit_id TEXT,
                  recorded_at TEXT NOT NULL,
                  case_type TEXT,
                  model TEXT NOT NULL,
                  input_tokens INTEGER NOT NULL,
                  output_tokens INTEGER NOT NULL,
                  latency_ms INTEGER NOT NULL,
                  call_started_at TEXT NOT NULL,
                  call_purpose TEXT NOT NULL,
                  call_status TEXT NOT NULL,
                  retry_attempt INTEGER NOT NULL,
                  prompt_version TEXT,
                  is_eval_case INTEGER NOT NULL,
                  eval_run_id TEXT,
                  is_test INTEGER NOT NULL DEFAULT 0,
                  demo_attack INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS audit_event (
                  audit_id TEXT PRIMARY KEY,
                  case_id TEXT NOT NULL,
                  supersedes_audit_id TEXT,
                  recorded_at TEXT NOT NULL,
                  trace_id TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  name TEXT NOT NULL,
                  detail_json TEXT NOT NULL,
                  verification_status TEXT
                );
                CREATE TABLE IF NOT EXISTS handoff (
                  handoff_id TEXT PRIMARY KEY,
                  case_id TEXT NOT NULL UNIQUE,
                  status TEXT NOT NULL,
                  packet TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  claimed_by TEXT,
                  resolution_note TEXT
                );
                CREATE TABLE IF NOT EXISTS confirmation (
                  confirmation_id TEXT PRIMARY KEY,
                  case_id TEXT NOT NULL,
                  action TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  UNIQUE (case_id, action)
                );
                CREATE TABLE IF NOT EXISTS card_block (
                  block_id TEXT PRIMARY KEY,
                  case_id TEXT NOT NULL,
                  customer_key TEXT NOT NULL,
                  product_key TEXT NOT NULL,
                  transaction_key TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS llm_price (
                  model TEXT NOT NULL,
                  usd_per_1m_input REAL NOT NULL,
                  usd_per_1m_output REAL NOT NULL,
                  effective_from TEXT NOT NULL,
                  source_url TEXT NOT NULL,
                  PRIMARY KEY (model, effective_from)
                );
                CREATE TABLE IF NOT EXISTS analytics_assumption (
                  key TEXT PRIMARY KEY,
                  value REAL NOT NULL,
                  note TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS test_cases (
                  case_id TEXT PRIMARY KEY,
                  marked_at TEXT NOT NULL,
                  reason TEXT
                );
                DROP VIEW IF EXISTS audit_live;
                DROP VIEW IF EXISTS audit_current;
                CREATE VIEW audit_current AS
                SELECT * FROM audit_case AS a
                WHERE NOT EXISTS (
                  SELECT 1 FROM audit_case AS newer
                  WHERE newer.supersedes_audit_id = a.audit_id
                );
                DROP VIEW IF EXISTS audit_llm_call_current;
                CREATE VIEW audit_llm_call_current AS
                SELECT * FROM audit_llm_call AS a
                WHERE NOT EXISTS (
                  SELECT 1 FROM audit_llm_call AS newer
                  WHERE newer.supersedes_audit_id = a.audit_id
                );
                """
            )
            for price in _PRICES:
                conn.execute(
                    "INSERT OR IGNORE INTO llm_price VALUES (?, ?, ?, ?, ?)",
                    price,
                )
            for assumption in _ASSUMPTIONS:
                conn.execute(
                    "INSERT OR IGNORE INTO analytics_assumption VALUES (?, ?, ?)",
                    assumption,
                )
            _add_sqlite_is_test(conn)
            _add_sqlite_judge(conn)
            conn.executescript(_SQLITE_AUDIT_VIEWS)

    def _ensure_postgres_is_test(self) -> None:
        """Apply migrations/002 when this role can. A refusal leaves startup up."""
        try:
            from app.db import connect_app
            from app.paths import project_root

            path = project_root() / "migrations" / "002_is_test.sql"
            statements = _sql_statements(path)
            with connect_app(self.dsn) as conn:
                column = conn.execute(
                    "SELECT 1 AS ok FROM information_schema.columns "
                    "WHERE table_schema = 'app' AND table_name = 'audit_case' "
                    "AND column_name = 'is_test'"
                ).fetchone()
                table = conn.execute(
                    "SELECT 1 AS ok FROM information_schema.tables "
                    "WHERE table_schema = 'app' AND table_name = 'test_cases'"
                ).fetchone()
                view = conn.execute(
                    "SELECT 1 AS ok FROM information_schema.views "
                    "WHERE table_schema = 'app' AND table_name = 'audit_live'"
                ).fetchone()
                if column and table and view:
                    return
                for statement in statements:
                    try:
                        conn.execute(statement)
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        logger.warning(
                            "is_test migration was not applied; "
                            "run migrations/002_is_test.sql as the database owner"
                        )
                        return
        except Exception as exc:
            logger.warning("is_test migration skipped (%s)", type(exc).__name__)

    def _ensure_postgres_judge(self) -> None:
        """Apply migrations/004 when this role can. A refusal leaves startup up."""
        try:
            from app.db import connect_app
            from app.paths import project_root

            path = project_root() / "migrations" / "004_demo_attack.sql"
            statements = _sql_statements(path)
            with connect_app(self.dsn) as conn:
                column = conn.execute(
                    "SELECT 1 AS ok FROM information_schema.columns "
                    "WHERE table_schema = 'app' AND table_name = 'cases' "
                    "AND column_name = 'demo_attack'"
                ).fetchone()
                draft = conn.execute(
                    "SELECT 1 AS ok FROM information_schema.columns "
                    "WHERE table_schema = 'app' AND table_name = 'cases' "
                    "AND column_name = 'reply_draft'"
                ).fetchone()
                if column and draft:
                    return
                for statement in statements:
                    try:
                        conn.execute(statement)
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        logger.warning(
                            "demo-attack migration was not applied; "
                            "run migrations/004_demo_attack.sql as the database owner"
                        )
                        return
        except Exception as exc:
            logger.warning("demo-attack migration skipped (%s)", type(exc).__name__)

    def _ensure_postgres_view_grants(self) -> None:
        """Apply migrations/003 when this role can. A refusal leaves startup up.

        migrations_ok stays the test-schema probe. View privileges are not
        folded into that flag.
        """
        try:
            from app.db import connect_app
            from app.paths import project_root

            path = project_root() / "migrations" / "003_view_grants.sql"
            statements = _sql_statements(path)
            with connect_app(self.dsn) as conn:
                if _privileges_are_select_only(_view_privileges(conn)):
                    return
                for statement in statements:
                    try:
                        conn.execute(statement)
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        logger.warning(
                            "view grants were not applied; "
                            "run migrations/003_view_grants.sql as the database owner"
                        )
                        return
        except Exception as exc:
            logger.warning("view grants migration skipped (%s)", type(exc).__name__)

    def insert_case(self, row: dict[str, Any]) -> None:
        self._insert_with_optional_test(
            "cases",
            "case_id, customer_key, transaction_key, state, language, case_type, "
            "created_at, updated_at, closed_at, latest_audit_id, is_eval_case, "
            "eval_run_id, case_source",
            (
                row["case_id"],
                row["customer_key"],
                row.get("transaction_key"),
                row["state"],
                row["language"],
                row.get("case_type"),
                row["created_at"],
                row["updated_at"],
                row.get("closed_at"),
                row.get("latest_audit_id"),
                bool(row.get("is_eval_case")),
                row.get("eval_run_id"),
                row.get("case_source"),
            ),
            is_test=bool(row.get("is_test")),
            extras=(("demo_attack", bool(row.get("demo_attack"))),),
        )

    def insert_test_case(self, case_id: str, reason: str | None = None) -> int:
        """Insert one case id. Returns the row count: 1 inserted, 0 already present."""
        if not self.migrations_ok:
            return 0
        try:
            return self._write(
                f"INSERT INTO {self._table('test_cases')} (case_id, marked_at, reason) "
                "VALUES (?, ?, ?) ON CONFLICT (case_id) DO NOTHING",
                (case_id, _now(), reason),
            )
        except Exception as exc:
            if not _missing_test_schema(exc):
                raise
            self._mark_migrations_missing()
            return 0

    def test_case_ids(self) -> set[str]:
        if not self.migrations_ok:
            return set()
        try:
            rows = self.execute(f"SELECT case_id FROM {self._table('test_cases')}")
        except Exception as exc:
            if not _missing_test_schema(exc):
                raise
            self._mark_migrations_missing()
            return set()
        return {str(row["case_id"]) for row in rows}

    def list_cases(self) -> list[dict[str, Any]]:
        rows = self.execute(f"SELECT * FROM {self._table('cases')}")
        return [_normalize_case(row) for row in rows]

    def update_case(self, case_id: str, fields: dict[str, Any]) -> None:
        allowed = {
            "state",
            "case_type",
            "language",
            "updated_at",
            "closed_at",
            "latest_audit_id",
            "transaction_key",
            "reply_draft",
            "reply_sent",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"case columns are not updated this way: {sorted(unknown)}")
        self._update_case_fields(case_id, fields)

    def _update_case_fields(self, case_id: str, fields: dict[str, Any]) -> None:
        assignments = ", ".join(f"{name} = ?" for name in fields)
        params = tuple(fields.values()) + (case_id,)
        try:
            self._write(
                f"UPDATE {self._table('cases')} SET {assignments} WHERE case_id = ?",
                params,
            )
        except Exception as exc:
            optional = {"reply_draft", "reply_sent"}
            if not optional.intersection(fields) or not _missing_added_column(exc):
                raise
            logger.warning("reply draft was not stored (%s)", type(exc).__name__)
            kept = {name: value for name, value in fields.items() if name not in optional}
            if kept:
                self._update_case_fields(case_id, kept)

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        rows = self.execute(
            f"SELECT * FROM {self._table('cases')} WHERE case_id = ?",
            (case_id,),
        )
        return _normalize_case(rows[0]) if rows else None

    def append_audit_case(self, row: dict[str, Any]) -> str:
        flags = row.get("guardrail_flags") or []
        flag_value: object
        if self.backend == "postgres":
            flag_value = list(flags)
        else:
            flag_value = json.dumps(list(flags))
        self._insert_with_optional_test(
            "audit_case",
            "audit_id, case_id, supersedes_audit_id, recorded_at, case_type, "
            "customer_segment, final_resolution_status, case_created_at, case_closed_at, "
            "decision, automation_attempted, handoff_reason, handoff_packet_complete, "
            "language, country, accent_group, rule_or_model_version, prompt_version, "
            "fraud_score, model_risk_score, guardrail_flags, is_eval_case, eval_run_id, "
            "case_source",
            (
                row["audit_id"],
                row["case_id"],
                row.get("supersedes_audit_id"),
                row.get("recorded_at") or _now(),
                row["case_type"],
                row.get("customer_segment"),
                row.get("final_resolution_status"),
                row["case_created_at"],
                row.get("case_closed_at"),
                row.get("decision"),
                bool(row.get("automation_attempted")),
                row.get("handoff_reason"),
                row.get("handoff_packet_complete"),
                row["language"],
                row.get("country"),
                row.get("accent_group"),
                row.get("rule_or_model_version"),
                row.get("prompt_version"),
                row.get("fraud_score"),
                row.get("model_risk_score"),
                flag_value,
                bool(row.get("is_eval_case")),
                row.get("eval_run_id"),
                row.get("case_source"),
            ),
            is_test=bool(row.get("is_test")),
            extras=(("demo_attack", bool(row.get("demo_attack"))),),
        )
        return str(row["audit_id"])

    def current_audit_cases(self) -> list[dict[str, Any]]:
        """Tips from audit_current. is_test comes from cases and test_cases.

        audit_current keeps the column list it had when it was created, so a
        later is_test column on audit_case is not on the view. The queue, the
        packet, and the admin include filters read the flag from cases and
        from test_cases membership instead.
        """
        raw = self.execute(f"SELECT * FROM {self._table('audit_current')}")
        rows = [_normalize_audit(row) for row in raw]
        if not rows:
            return rows
        cases = self.list_cases()
        flags = {str(row["case_id"]): bool(row.get("is_test")) for row in cases}
        attacks = {str(row["case_id"]): bool(row.get("demo_attack")) for row in cases}
        marked = self.test_case_ids()
        for row in rows:
            case_id = str(row.get("case_id") or "")
            row["is_test"] = flags.get(case_id, False) or case_id in marked
            row["demo_attack"] = bool(row.get("demo_attack")) or attacks.get(case_id, False)
        return rows

    def live_audit_cases(self) -> list[dict[str, Any]]:
        """audit_current minus insert-time test rows, marked case ids, and eval tips."""
        if not self.migrations_ok:
            return self.current_audit_cases()
        try:
            raw = self.execute(f"SELECT * FROM {self._table('audit_live')}")
        except Exception as exc:
            if not _missing_test_schema(exc):
                raise
            self._mark_migrations_missing()
            return self.current_audit_cases()
        rows = [_normalize_audit(row) for row in raw]
        attacks = {str(row["case_id"]): bool(row.get("demo_attack")) for row in self.list_cases()}
        kept: list[dict[str, Any]] = []
        for row in rows:
            case_id = str(row.get("case_id") or "")
            if bool(row.get("demo_attack")) or attacks.get(case_id, False):
                continue
            kept.append(row)
        return kept

    def audit_chain(self, case_id: str) -> list[dict[str, Any]]:
        """Tip from audit_current, then each superseded parent. Read-only."""
        tips = self.execute(
            f"SELECT * FROM {self._table('audit_current')} WHERE case_id = ?",
            (case_id,),
        )
        found: dict[str, dict[str, Any]] = {}
        for tip in tips:
            self._walk_supersedes(_normalize_audit(tip), found, 0)
        return list(found.values())

    def _walk_supersedes(
        self, row: dict[str, Any], found: dict[str, dict[str, Any]], depth: int
    ) -> None:
        audit_id = str(row.get("audit_id") or "")
        if not audit_id or audit_id in found or depth > 40:
            return
        found[audit_id] = row
        previous = row.get("supersedes_audit_id")
        if not previous:
            return
        older = self.execute(
            f"SELECT * FROM {self._table('audit_case')} WHERE audit_id = ?",
            (str(previous),),
        )
        if not older:
            return
        self._walk_supersedes(_normalize_audit(older[0]), found, depth + 1)

    def audit_case_count(self, case_id: str) -> int:
        rows = self.execute(
            f"SELECT count(*) AS n FROM {self._table('audit_case')} WHERE case_id = ?",
            (case_id,),
        )
        return int(rows[0]["n"])

    def append_event(self, row: dict[str, Any]) -> None:
        detail = json.dumps(row.get("detail") or {}, default=str)
        self._write(
            f"INSERT INTO {self._table('audit_event')} ("
            "audit_id, case_id, supersedes_audit_id, recorded_at, trace_id, kind, name, "
            "detail_json, verification_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row["audit_id"],
                row["case_id"],
                row.get("supersedes_audit_id"),
                row.get("recorded_at") or _now(),
                row["trace_id"],
                row["kind"],
                row["name"],
                detail,
                row.get("verification_status"),
            ),
        )

    def list_events(self, case_id: str) -> list[dict[str, Any]]:
        return self.execute(
            f"SELECT * FROM {self._table('audit_event')} WHERE case_id = ? ORDER BY recorded_at",
            (case_id,),
        )

    def append_llm_call(self, row: dict[str, Any]) -> None:
        self._insert_with_optional_test(
            "audit_llm_call",
            "audit_id, llm_call_id, case_id, supersedes_audit_id, recorded_at, case_type, "
            "model, input_tokens, output_tokens, latency_ms, call_started_at, call_purpose, "
            "call_status, retry_attempt, prompt_version, is_eval_case, eval_run_id",
            (
                row["audit_id"],
                row["llm_call_id"],
                row["case_id"],
                row.get("supersedes_audit_id"),
                row.get("recorded_at") or _now(),
                row.get("case_type"),
                row["model"],
                int(row.get("input_tokens") or 0),
                int(row.get("output_tokens") or 0),
                int(row.get("latency_ms") or 0),
                row["call_started_at"],
                row["call_purpose"],
                row["call_status"],
                int(row.get("retry_attempt") or 0),
                row.get("prompt_version"),
                bool(row.get("is_eval_case")),
                row.get("eval_run_id"),
            ),
            is_test=bool(row.get("is_test")),
            extras=(("demo_attack", bool(row.get("demo_attack"))),),
        )

    def current_llm_calls(self) -> list[dict[str, Any]]:
        return self.execute(f"SELECT * FROM {self._table('audit_llm_call_current')}")

    def insert_confirmation(self, confirmation_id: str, case_id: str, action: str) -> None:
        self._write(
            f"INSERT INTO {self._table('confirmation')} "
            "(confirmation_id, case_id, action, created_at) VALUES (?, ?, ?, ?)",
            (confirmation_id, case_id, action, _now()),
        )

    def has_confirmation(self, case_id: str, action: str) -> bool:
        rows = self.execute(
            f"SELECT confirmation_id FROM {self._table('confirmation')} "
            "WHERE case_id = ? AND action = ?",
            (case_id, action),
        )
        return bool(rows)

    def insert_block(self, row: dict[str, Any]) -> None:
        self._write(
            f"INSERT INTO {self._table('card_block')} ("
            "block_id, case_id, customer_key, product_key, transaction_key, status, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                row["block_id"],
                row["case_id"],
                row["customer_key"],
                row["product_key"],
                row["transaction_key"],
                row["status"],
                _now(),
            ),
        )

    def get_block(self, case_id: str) -> dict[str, Any] | None:
        rows = self.execute(
            f"SELECT * FROM {self._table('card_block')} WHERE case_id = ? ORDER BY created_at DESC",
            (case_id,),
        )
        row = rows[0] if rows else None
        if self.readback_tamper is not None:
            return self.readback_tamper(row)
        return row

    def insert_handoff(self, row: dict[str, Any]) -> None:
        packet = row["packet"]
        payload = packet if isinstance(packet, str) else json.dumps(packet)
        self._write(
            f"INSERT INTO {self._table('handoff')} ("
            "handoff_id, case_id, status, packet, created_at, updated_at, "
            "claimed_by, resolution_note"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row["handoff_id"],
                row["case_id"],
                row["status"],
                payload,
                row["created_at"],
                row["updated_at"],
                row.get("claimed_by"),
                row.get("resolution_note"),
            ),
        )

    def update_handoff(self, case_id: str, fields: dict[str, Any]) -> None:
        allowed = {"status", "updated_at", "claimed_by", "resolution_note"}
        if set(fields) - allowed:
            raise ValueError("handoff packet is not rewritten in place")
        assignments = ", ".join(f"{name} = ?" for name in fields)
        self._write(
            f"UPDATE {self._table('handoff')} SET {assignments} WHERE case_id = ?",
            tuple(fields.values()) + (case_id,),
        )

    def get_handoff(self, case_id: str) -> dict[str, Any] | None:
        rows = self.execute(
            f"SELECT * FROM {self._table('handoff')} WHERE case_id = ?",
            (case_id,),
        )
        if not rows:
            return None
        return _normalize_handoff(rows[0])

    def list_handoffs(self) -> list[dict[str, Any]]:
        rows = self.execute(f"SELECT * FROM {self._table('handoff')} ORDER BY created_at DESC")
        return [_normalize_handoff(row) for row in rows]

    def prices(self) -> list[dict[str, Any]]:
        return self.execute(f"SELECT * FROM {self._table('llm_price')}")

    def assumptions(self) -> dict[str, float]:
        rows = self.execute(f"SELECT key, value FROM {self._table('analytics_assumption')}")
        return {str(row["key"]): float(row["value"]) for row in rows}


_SQLITE_AUDIT_VIEWS = """
DROP VIEW IF EXISTS audit_live;
DROP VIEW IF EXISTS audit_current;
CREATE VIEW audit_current AS
SELECT * FROM audit_case AS a
WHERE NOT EXISTS (
  SELECT 1 FROM audit_case AS newer
  WHERE newer.supersedes_audit_id = a.audit_id
);
DROP VIEW IF EXISTS audit_llm_call_current;
CREATE VIEW audit_llm_call_current AS
SELECT * FROM audit_llm_call AS a
WHERE NOT EXISTS (
  SELECT 1 FROM audit_llm_call AS newer
  WHERE newer.supersedes_audit_id = a.audit_id
);
CREATE VIEW audit_live AS
SELECT cur.*
FROM audit_current AS cur
WHERE cur.eval_run_id IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM audit_case AS src
    WHERE src.audit_id = cur.audit_id AND src.is_test = 1
  )
  AND NOT EXISTS (
    SELECT 1 FROM test_cases AS marked
    WHERE marked.case_id = cur.case_id
  )
  AND NOT EXISTS (
    SELECT 1 FROM audit_case AS src
    WHERE src.audit_id = cur.audit_id AND src.demo_attack = 1
  )
  AND NOT EXISTS (
    SELECT 1 FROM cases AS marked_case
    WHERE marked_case.case_id = cur.case_id AND marked_case.demo_attack = 1
  );
"""

_SQL_COMMENT = re.compile(r"--.*?$", re.MULTILINE)


def _add_sqlite_is_test(conn: sqlite3.Connection) -> None:
    for table in ("cases", "audit_case", "audit_llm_call"):
        columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
        if "is_test" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN is_test INTEGER NOT NULL DEFAULT 0")


def _add_sqlite_judge(conn: sqlite3.Connection) -> None:
    for table in ("cases", "audit_case", "audit_llm_call"):
        columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
        if "demo_attack" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN demo_attack INTEGER NOT NULL DEFAULT 0")
    case_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(cases)")}
    if "reply_draft" not in case_columns:
        conn.execute("ALTER TABLE cases ADD COLUMN reply_draft TEXT")
    if "reply_sent" not in case_columns:
        conn.execute("ALTER TABLE cases ADD COLUMN reply_sent TEXT")


def _sql_statements(path: Path) -> list[str]:
    """Split a migration on semicolons that are outside dollar quotes."""
    cleaned = _SQL_COMMENT.sub("", path.read_text(encoding="utf-8"))
    statements: list[str] = []
    buf: list[str] = []
    in_dollar = False
    index = 0
    while index < len(cleaned):
        if cleaned.startswith("$$", index):
            in_dollar = not in_dollar
            buf.append("$$")
            index += 2
            continue
        char = cleaned[index]
        if char == ";" and not in_dollar:
            statement = "".join(buf).strip()
            if statement:
                statements.append(statement)
            buf = []
            index += 1
            continue
        buf.append(char)
        index += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


_AUDIT_VIEWS = ("audit_current", "audit_live", "audit_llm_call_current")


def _view_privileges(conn: Any) -> dict[str, set[str]]:
    rows = conn.execute(
        "SELECT table_name, privilege_type FROM information_schema.table_privileges "
        "WHERE table_schema = 'app' AND grantee = 'app_rw' "
        "AND table_name IN ('audit_current', 'audit_live', 'audit_llm_call_current')"
    ).fetchall()
    found: dict[str, set[str]] = {}
    for row in rows:
        name = str(row["table_name"])
        found.setdefault(name, set()).add(str(row["privilege_type"]).upper())
    return found


def _privileges_are_select_only(found: dict[str, set[str]]) -> bool:
    if set(found) != set(_AUDIT_VIEWS):
        return False
    return all(privileges == {"SELECT"} for privileges in found.values())


def _placeholders(count: int) -> str:
    return ", ".join("?" for _ in range(count))


def _missing_added_column(exc: BaseException) -> bool:
    text = str(exc).lower()
    markers = ("no such column", "no column", "does not exist", "undefined column")
    return any(marker in text for marker in markers)


def _missing_test_schema(exc: BaseException) -> bool:
    text = str(exc).lower()
    names = ("is_test", "test_cases", "audit_live")
    markers = ("no such", "does not exist", "undefined")
    return any(name in text for name in names) and any(marker in text for marker in markers)


def _sqlite_has_test_schema(conn: sqlite3.Connection) -> bool:
    def columns(table: str) -> set[str]:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}

    names = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
    }
    return (
        "is_test" in columns("cases")
        and "is_test" in columns("audit_case")
        and "is_test" in columns("audit_llm_call")
        and "test_cases" in names
        and "audit_live" in names
    )


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "True"):
        return True
    return False


def _as_optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    return _as_bool(value)


def _normalize_case(row: dict[str, Any]) -> dict[str, Any]:
    row["is_eval_case"] = _as_bool(row.get("is_eval_case"))
    row["is_test"] = _as_bool(row.get("is_test"))
    row["demo_attack"] = _as_bool(row.get("demo_attack"))
    return row


def _normalize_audit(row: dict[str, Any]) -> dict[str, Any]:
    row["is_eval_case"] = _as_bool(row.get("is_eval_case"))
    row["is_test"] = _as_bool(row.get("is_test"))
    row["demo_attack"] = _as_bool(row.get("demo_attack"))
    row["automation_attempted"] = _as_bool(row.get("automation_attempted"))
    row["handoff_packet_complete"] = _as_optional_bool(row.get("handoff_packet_complete"))
    row["guardrail_flags"] = _flags_out(row.get("guardrail_flags"))
    return row


def _normalize_handoff(row: dict[str, Any]) -> dict[str, Any]:
    packet = row.get("packet")
    if isinstance(packet, str):
        row["packet"] = json.loads(packet)
    return row
