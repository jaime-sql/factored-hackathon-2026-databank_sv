"""Reject statements the app_rw role is not allowed to run.

Audit tables are append-only. Corrections are new rows. Nothing is deleted.
"""

from __future__ import annotations

import re

AUDIT_TABLES = (
    "audit_case",
    "audit_llm_call",
    "audit_event",
    "audit_current",
    "audit_llm_call_current",
    "audit_agent_step",
)
INSERT_ONLY_TABLES = ("test_cases",)


class AuditImmutable(RuntimeError):
    """An audit write tried to change history instead of appending a row."""


_COMMENT = re.compile(r"--.*?$|/\*.*?\*/", re.MULTILINE | re.DOTALL)


def assert_statement_allowed(sql: str) -> None:
    stripped = _COMMENT.sub(" ", sql)
    parts = stripped.lstrip().split(None, 1)
    if not parts:
        return
    head = parts[0].lower()
    lowered = stripped.lower()
    if head == "delete":
        raise AuditImmutable("DELETE is not permitted")
    if head in {"drop", "truncate", "alter"}:
        raise AuditImmutable("schema changes are not permitted at runtime")
    if head == "update":
        for table in AUDIT_TABLES:
            if re.search(rf"\b{table}\b", lowered):
                raise AuditImmutable(
                    f"{table} is append-only; insert a row with supersedes_audit_id"
                )
        for table in INSERT_ONLY_TABLES:
            if re.search(rf"\b{table}\b", lowered):
                raise AuditImmutable(f"{table} accepts INSERT and SELECT only")
