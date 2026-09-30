"""SQLite and Postgres operational store.

Audit rows are inserted, never updated. A correction is a new row whose
supersedes_audit_id points at the row it replaces. KPIs read audit_current,
the tip of each chain. SQLite mirrors that rule in this process because it
has no roles.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.ops.guard import assert_statement_allowed

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
        if backend == "sqlite":
            self._init_sqlite()

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

    def _write(self, sql: str, params: tuple[object, ...]) -> None:
        assert_statement_allowed(sql)
        params = self._params(params)
        query = self._q(sql)
        if self.backend == "sqlite":
            with sqlite3.connect(self.path) as conn:
                conn.execute(query, params)
            return
        from app.db import connect_app

        with connect_app(self.dsn) as conn:
            conn.execute(query, params)
            conn.commit()

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
                  case_source TEXT
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
                  case_source TEXT
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
                  eval_run_id TEXT
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

    def insert_case(self, row: dict[str, Any]) -> None:
        sql = (
            f"INSERT INTO {self._table('cases')} ("
            "case_id, customer_key, transaction_key, state, language, case_type, "
            "created_at, updated_at, closed_at, latest_audit_id, is_eval_case, "
            "eval_run_id, case_source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        self._write(
            sql,
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
        )

    def update_case(self, case_id: str, fields: dict[str, Any]) -> None:
        allowed = {
            "state",
            "case_type",
            "language",
            "updated_at",
            "closed_at",
            "latest_audit_id",
            "transaction_key",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"case columns are not updated this way: {sorted(unknown)}")
        assignments = ", ".join(f"{name} = ?" for name in fields)
        params = tuple(fields.values()) + (case_id,)
        self._write(
            f"UPDATE {self._table('cases')} SET {assignments} WHERE case_id = ?",
            params,
        )

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
        sql = (
            f"INSERT INTO {self._table('audit_case')} ("
            "audit_id, case_id, supersedes_audit_id, recorded_at, case_type, "
            "customer_segment, final_resolution_status, case_created_at, case_closed_at, "
            "decision, automation_attempted, handoff_reason, handoff_packet_complete, "
            "language, country, accent_group, rule_or_model_version, prompt_version, "
            "fraud_score, model_risk_score, guardrail_flags, is_eval_case, eval_run_id, "
            "case_source) VALUES ("
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        self._write(
            sql,
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
        )
        return str(row["audit_id"])

    def current_audit_cases(self) -> list[dict[str, Any]]:
        rows = self.execute(f"SELECT * FROM {self._table('audit_current')}")
        return [_normalize_audit(row) for row in rows]

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
        self._write(
            f"INSERT INTO {self._table('audit_llm_call')} ("
            "audit_id, llm_call_id, case_id, supersedes_audit_id, recorded_at, case_type, "
            "model, input_tokens, output_tokens, latency_ms, call_started_at, call_purpose, "
            "call_status, retry_attempt, prompt_version, is_eval_case, eval_run_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
    return row


def _normalize_audit(row: dict[str, Any]) -> dict[str, Any]:
    row["is_eval_case"] = _as_bool(row.get("is_eval_case"))
    row["automation_attempted"] = _as_bool(row.get("automation_attempted"))
    row["handoff_packet_complete"] = _as_optional_bool(row.get("handoff_packet_complete"))
    row["guardrail_flags"] = _flags_out(row.get("guardrail_flags"))
    return row


def _normalize_handoff(row: dict[str, Any]) -> dict[str, Any]:
    packet = row.get("packet")
    if isinstance(packet, str):
        row["packet"] = json.loads(packet)
    return row
