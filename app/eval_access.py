"""Eval-runner fields are stored only when the runner proves it holds the token."""

from __future__ import annotations

import secrets

from app.errors import APIError

CASE_SOURCES = frozenset({"sample", "synthetic_dup", "red_team", "ood_sv_text", "pt_translated"})
DEMO_SAMPLE_LABEL = "Demo sample (fraud-enriched, ~11x HIGH rate vs full data)"


def accept_eval_fields(
    header_token: str | None,
    expected_token: str,
    eval_run_id: str | None,
    case_source: str | None,
) -> tuple[str | None, str | None]:
    """Return (eval_run_id, case_source) to store.

    A missing or wrong token drops both values. The case is still opened.
    """
    expected = expected_token.strip()
    presented = (header_token or "").strip()
    if not expected or not presented or not secrets.compare_digest(presented, expected):
        return None, None
    run = (eval_run_id or "").strip() or None
    source = (case_source or "").strip() or None
    if run is not None and (len(run) > 80 or any(ch.isspace() for ch in run)):
        raise APIError(422, "invalid_eval_run_id", "eval_run_id is not usable")
    if source is not None and source not in CASE_SOURCES:
        raise APIError(422, "invalid_case_source", "case_source is not a known eval source")
    return run, source
