"""Customer intake, agent queue, and metrics."""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.auth.session import agent_role, read_customer, sign_customer
from app.bank.fixture import PERSONAS
from app.config import Settings
from app.errors import APIError
from app.eval_access import accept_eval_fields
from app.handoff.present import packet_view, queue_card
from app.metrics.compute import compute_metrics
from app.timeutil import present_time

router = APIRouter()


class SessionIn(BaseModel):
    persona: str


class CaseIn(BaseModel):
    transaction_key: str | None = None
    message: str = ""
    language: str | None = None
    eval_run_id: str | None = None
    case_source: str | None = None
    case_id: str | None = None


class ActionIn(BaseModel):
    action: str = Field(min_length=1, max_length=64)


class ResolveIn(BaseModel):
    note: str = Field(default="", max_length=500)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _customer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    token = header.removeprefix("Bearer ").strip() if header.lower().startswith("bearer ") else ""
    if not token:
        token = request.cookies.get("hd_session", "")
    customer_key = read_customer(_settings(request).session_secret, token)
    if customer_key is None:
        raise APIError(401, "auth_required", "Sign in again")
    return customer_key


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header.removeprefix("Bearer ").strip()
    return ""


def _agent(request: Request, *, admin_only: bool = False) -> str:
    role = agent_role(_settings(request), _bearer(request))
    if role is None:
        raise APIError(401, "auth_required", "Agent sign-in required")
    if admin_only and role != "admin":
        raise APIError(403, "forbidden", "Admin token required")
    return role


def _health(request: Request) -> dict[str, str]:
    settings = _settings(request)
    return {
        "status": "ok",
        "bank": "postgres" if settings.database_url else "sqlite",
        "ops": "postgres" if settings.database_url else "sqlite",
        "llm": settings.resolved_llm_provider(),
    }


@router.get("/healthz")
def healthz(request: Request) -> dict[str, str]:
    return _health(request)


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    return _health(request)


@router.get("/api/auth/config")
def auth_config(request: Request) -> dict[str, str]:
    settings = _settings(request)
    role = agent_role(settings, _bearer(request))
    if role == "judge":
        raise APIError(403, "forbidden", "Admin token required")
    payload = {"agent_auth": "clerk" if settings.clerk_configured else "demo"}
    if settings.environment != "production" and not settings.clerk_configured:
        payload["demo_token"] = settings.demo_agent_token
    return payload


@router.get("/api/personas")
def personas(request: Request) -> dict[str, Any]:
    postgres = bool(_settings(request).database_url.strip())
    return {
        "personas": [
            {
                "id": row["id"],
                "label": row["label"],
                "country": row["country"],
                "tz": row["tz"],
                "segment": row["segment"],
                "note": (
                    (row.get("bank_note") or "Challenge data customer") if postgres else row["note"]
                ),
            }
            for row in PERSONAS
        ]
    }


@router.post("/api/session")
def open_session(body: SessionIn, request: Request) -> JSONResponse:
    match = next((row for row in PERSONAS if row["id"] == body.persona), None)
    if match is None:
        raise APIError(404, "not_found", "Unknown persona")
    settings = _settings(request)
    session_key = (
        match["bank_customer_key"] if settings.database_url.strip() else match["customer_key"]
    )
    token = sign_customer(settings.session_secret, session_key, settings.session_ttl_hours)
    response = JSONResponse(
        {
            "persona": match["id"],
            "label": match["label"],
            "tz": match["tz"],
            "token": token,
        }
    )
    response.set_cookie("hd_session", token, httponly=True, samesite="lax")
    return response


@router.get("/api/transactions")
def transactions(request: Request) -> dict[str, Any]:
    customer_key = _customer(request)
    customer = request.app.state.bank.get_customer(customer_key)
    if customer is None:
        raise APIError(404, "not_found", "Customer not found")
    rows = []
    for tx in request.app.state.bank.get_transactions(customer_key):
        shown = present_time(tx.transaction_ts_utc, customer.tz, customer.customer_country, "es")
        rows.append(
            {
                "transaction_key": tx.transaction_key,
                "merchant_name": tx.merchant_name,
                "merchant_category": tx.merchant_category,
                "amount": tx.amount,
                "currency": tx.currency,
                "transaction_city": tx.transaction_city,
                "transaction_country": tx.transaction_country,
                "transaction_status": tx.transaction_status,
                "customer_tz": shown["tz"],
                "local_time": shown["label"],
                "utc": shown["utc"],
                "abbreviation": shown["abbreviation"],
            }
        )
    return {"customer_tz": customer.tz, "transactions": rows}


@router.post("/cases")
def open_case(
    body: CaseIn,
    request: Request,
    eval_runner_token: str | None = Header(default=None, alias="EVAL_RUNNER_TOKEN"),
) -> dict[str, Any]:
    customer_key = _customer(request)
    eval_run_id, case_source = accept_eval_fields(
        eval_runner_token,
        _settings(request).eval_runner_token,
        body.eval_run_id,
        body.case_source,
    )
    result = request.app.state.engine.open_case(
        customer_key,
        body.transaction_key,
        body.message,
        body.language,
        eval_run_id,
        case_source,
    )
    return result.as_dict()


@router.post("/cases/{case_id}/actions")
def act(case_id: str, body: ActionIn, request: Request) -> dict[str, Any]:
    customer_key = _customer(request)
    return request.app.state.engine.act(customer_key, case_id, body.action).as_dict()


@router.get("/cases/{case_id}")
def get_case(case_id: str, request: Request) -> dict[str, Any]:
    customer_key = _customer(request)
    case = request.app.state.ops.get_case(case_id)
    if case is None or case["customer_key"] != customer_key:
        raise APIError(404, "not_found", "Case not found")
    return {
        "case_id": case["case_id"],
        "state": case["state"],
        "case_type": case["case_type"],
        "language": case["language"],
        "eval_run_id": case.get("eval_run_id"),
        "case_source": case.get("case_source"),
        "is_eval_case": case.get("is_eval_case"),
    }


def _audit_for(request: Request, case_id: str) -> dict[str, Any] | None:
    for row in request.app.state.ops.current_audit_cases():
        if row.get("case_id") == case_id:
            return row
    return None


def _thresholds(request: Request) -> tuple[float, float]:
    config = request.app.state.thresholds.get()
    return config.t_low, config.high_value


@router.get("/api/handoff")
def handoff_queue(request: Request) -> dict[str, Any]:
    _agent(request)
    audits = {row["case_id"]: row for row in request.app.state.ops.current_audit_cases()}
    items = [
        queue_card(row, audits.get(row["case_id"])) for row in request.app.state.ops.list_handoffs()
    ]
    return {"queue": items}


@router.get("/api/handoff/{case_id}")
def handoff_case(case_id: str, request: Request) -> dict[str, Any]:
    _agent(request)
    row = request.app.state.ops.get_handoff(case_id)
    if row is None:
        raise APIError(404, "not_found", "Handoff not found")
    events = request.app.state.ops.list_events(case_id)
    safe_events = [
        {
            "kind": event["kind"],
            "name": event["name"],
            "verification_status": event["verification_status"],
            "recorded_at": event["recorded_at"],
        }
        for event in events
    ]
    t_low, high_value = _thresholds(request)
    return {
        "handoff": row,
        "events": safe_events,
        "view": packet_view(row, _audit_for(request, case_id), t_low=t_low, high_value=high_value),
    }


@router.post("/api/handoff/{case_id}/claim")
def claim(case_id: str, request: Request) -> dict[str, str]:
    _agent(request)
    if request.app.state.ops.get_handoff(case_id) is None:
        raise APIError(404, "not_found", "Handoff not found")
    from datetime import UTC, datetime

    request.app.state.ops.update_handoff(
        case_id,
        {
            "status": "claimed",
            "claimed_by": _settings(request).demo_agent_email,
            "updated_at": datetime.now(UTC),
        },
    )
    return {"status": "claimed"}


@router.post("/api/handoff/{case_id}/resolve")
def resolve_handoff(case_id: str, body: ResolveIn, request: Request) -> dict[str, str]:
    _agent(request)
    if request.app.state.ops.get_handoff(case_id) is None:
        raise APIError(404, "not_found", "Handoff not found")
    from datetime import UTC, datetime

    request.app.state.ops.update_handoff(
        case_id,
        {
            "status": "resolved",
            "resolution_note": body.note,
            "updated_at": datetime.now(UTC),
        },
    )
    return {"status": "resolved"}


@router.get("/api/metrics")
def metrics(request: Request, include_eval: bool = False) -> dict[str, Any]:
    # Public on purpose: aggregates only, no per-customer rows or PII.
    ops = request.app.state.ops
    return compute_metrics(
        ops.current_audit_cases(),
        ops.current_llm_calls(),
        ops.prices(),
        ops.assumptions(),
        include_eval=include_eval,
    )


@router.get("/audit/export")
def export_audit(request: Request, include_eval: bool = False) -> Response:
    _agent(request, admin_only=True)
    rows = request.app.state.ops.current_audit_cases()
    if not include_eval:
        rows = [row for row in rows if not row.get("is_eval_case")]
    buffer = io.StringIO()
    fieldnames = [
        "audit_id",
        "case_id",
        "supersedes_audit_id",
        "case_type",
        "customer_segment",
        "decision",
        "handoff_reason",
        "language",
        "country",
        "is_eval_case",
        "eval_run_id",
        "case_source",
        "rule_or_model_version",
        "guardrail_flags",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: ("|".join(row[key]) if key == "guardrail_flags" else row.get(key))
                for key in fieldnames
            }
        )
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_current.csv"},
    )
