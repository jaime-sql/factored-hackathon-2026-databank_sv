"""Mark existing demo cases as test traffic.

Does not delete rows and does not run on startup. Pass case ids, a cutoff, or both.

    uv run python scripts/mark_demo_cases_test.py CASE_ID [CASE_ID ...]
    uv run python scripts/mark_demo_cases_test.py --before 2026-10-01T00:00:00Z
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.ids import new_case_id
from app.ops.store import OpsStore
from app.paths import project_root


def _stamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        stamp = value
    elif isinstance(value, str) and value.strip():
        stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    else:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp


def _parse_before(value: str) -> datetime:
    stamp = _stamp(value)
    if stamp is None:
        raise ValueError(f"not a timestamp: {value}")
    return stamp


def mark_cases_test(
    ops: OpsStore,
    case_ids: list[str] | None = None,
    before: datetime | None = None,
) -> list[str]:
    """Set is_test on matching cases and append an audit tip. Nothing is deleted."""
    if not case_ids and before is None:
        raise ValueError("pass case ids or before")
    wanted = {item.strip() for item in (case_ids or []) if item.strip()}
    tips = {str(row["case_id"]): row for row in ops.current_audit_cases()}
    updated: list[str] = []
    seen: set[str] = set()
    for case in ops.list_cases():
        case_id = str(case["case_id"])
        seen.add(case_id)
        by_id = case_id in wanted
        created = _stamp(case.get("created_at"))
        by_time = before is not None and created is not None and created < before
        if wanted and before is not None:
            if not (by_id or by_time):
                continue
        elif wanted:
            if not by_id:
                continue
        elif not by_time:
            continue
        ops.mark_case_test(case_id)
        tip = tips.get(case_id)
        if tip is not None and not tip.get("is_test"):
            audit_id = new_case_id()
            copied: dict[str, Any] = dict(tip)
            copied["audit_id"] = audit_id
            copied["supersedes_audit_id"] = tip["audit_id"]
            copied["is_test"] = True
            copied["recorded_at"] = datetime.now(UTC)
            ops.append_audit_case(copied)
            ops.update_case(case_id, {"latest_audit_id": audit_id, "updated_at": datetime.now(UTC)})
        updated.append(case_id)
    missing = sorted(wanted - seen)
    for case_id in missing:
        print(f"not found: {case_id}", file=sys.stderr)
    return updated


def _store(settings: Settings) -> OpsStore:
    if settings.database_url.strip():
        return OpsStore("postgres", dsn=settings.database_url)
    path = settings.ops_db_path or str(project_root() / "data" / "ops.sqlite")
    return OpsStore("sqlite", path=path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mark demo cases as test traffic")
    parser.add_argument("case_ids", nargs="*", help="case ids to mark")
    parser.add_argument("--before", help="also mark cases created before this timestamp")
    args = parser.parse_args(argv)
    if not args.case_ids and not args.before:
        parser.error("pass case ids or --before")
    before = _parse_before(args.before) if args.before else None
    updated = mark_cases_test(_store(Settings()), args.case_ids, before)
    print(f"marked {len(updated)} case(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
