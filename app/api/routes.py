"""Customer intake, agent queue, and metrics."""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.auth.session import (
    accepts_qa_test_token,
    agent_role,
    read_customer,
    read_session,
    read_test_marker,
    sign_customer,
    sign_test_marker,
)
from app.bank.fixture import PERSONAS
from app.cases.trail import build_steps
from app.config import Settings
from app.errors import APIError
from app.eval_access import accept_eval_fields
from app.guardrails.draft_check import grounded
from app.handoff.packet import HandoffPacket
from app.handoff.present import packet_view, queue_card
from app.i18n import (
    localize_metrics,
    merchant_label,
    money,
    persona_label,
    persona_note,
    place_label,
    transaction_status_label,
    ui_catalog,
    ui_copy,
)
from app.metrics.compute import compute_metrics, select_cases
from app.panels import fairness_panel, simulator_panel, trust_panel
from app.reply.draft import fact_sheet
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
    demo_attack: bool = False


class ActionIn(BaseModel):
    action: str = Field(min_length=1, max_length=64)


class ResolveIn(BaseModel):
    note: str = Field(default="", max_length=500)


class ReplyIn(BaseModel):
    text: str = Field(default="", max_length=2000)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _session_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    token = header.removeprefix("Bearer ").strip() if header.lower().startswith("bearer ") else ""
    # Agent tokens are not customer sessions. A judge bearer must not hide the cookie.
    if token and agent_role(_settings(request), token) is None:
        return token
    return request.cookies.get("hd_session", "")


def _customer(request: Request) -> str:
    customer_key = read_customer(_settings(request).session_secret, _session_token(request))
    if customer_key is None:
        raise APIError(401, "auth_required", "Sign in again")
    return customer_key


def _traffic_is_test(request: Request) -> bool:
    settings = _settings(request)
    if accepts_qa_test_token(settings.qa_test_token, request.headers.get("x-test-token", "")):
        return True
    if read_test_marker(settings.session_secret, request.cookies.get("hd_test", "")):
        return True
    session = read_session(settings.session_secret, _session_token(request))
    return bool(session and session[1])


def _arm_test_cookie(response: JSONResponse, request: Request) -> None:
    settings = _settings(request)
    response.set_cookie(
        "hd_test",
        sign_test_marker(settings.session_secret, settings.session_ttl_hours),
        httponly=True,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


def _admin_include(request: Request, requested: bool) -> bool:
    if not requested:
        return False
    return agent_role(_settings(request), _bearer(request)) == "admin"


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header.removeprefix("Bearer ").strip()
    return ""


def _console_source(request: Request) -> str | None:
    if agent_role(_settings(request), _bearer(request)) == "judge":
        return "judge"
    return None


def _record_console(request: Request, case_id: str, action: str) -> None:
    request.app.state.engine.record_console_action(case_id, action, _console_source(request))


def _agent(request: Request, *, admin_only: bool = False) -> str:
    role = agent_role(_settings(request), _bearer(request))
    if role is None:
        raise APIError(401, "auth_required", "Agent sign-in required")
    if admin_only and role != "admin":
        raise APIError(403, "forbidden", "Admin token required")
    return role


def _health(request: Request) -> dict[str, Any]:
    settings = _settings(request)
    ops = request.app.state.ops
    return {
        "status": "ok",
        "bank": "postgres" if settings.database_url else "sqlite",
        "ops": "postgres" if settings.database_url else "sqlite",
        "llm": settings.resolved_llm_provider(),
        "migrations_ok": bool(getattr(ops, "migrations_ok", False)),
    }


@router.get("/healthz")
def healthz(request: Request) -> dict[str, Any]:
    return _health(request)


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
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


def _ui_lang(language: str | None) -> str:
    return "pt" if language == "pt" else "es"


@router.get("/api/i18n")
def i18n_catalog() -> dict[str, dict[str, object]]:
    return ui_catalog()


@router.get("/api/personas")
def personas(request: Request) -> dict[str, Any]:
    postgres = bool(_settings(request).database_url.strip())
    return {
        "personas": [
            {
                "id": row["id"],
                "label": persona_label("es", row["id"], row["label"]),
                "labels": {
                    "es": persona_label("es", row["id"], row["label"]),
                    "pt": persona_label("pt", row["id"], row["label"]),
                },
                "country": row["country"],
                "tz": row["tz"],
                "segment": row["segment"],
                "note": persona_note("es", row["id"], postgres=postgres),
                "notes": {
                    "es": persona_note("es", row["id"], postgres=postgres),
                    "pt": persona_note("pt", row["id"], postgres=postgres),
                },
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
    is_test = _traffic_is_test(request)
    token = sign_customer(
        settings.session_secret, session_key, settings.session_ttl_hours, is_test=is_test
    )
    response = JSONResponse(
        {
            "persona": match["id"],
            "label": match["label"],
            "tz": match["tz"],
            "token": token,
            "is_test": is_test,
        }
    )
    response.set_cookie(
        "hd_session",
        token,
        httponly=True,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    if is_test:
        _arm_test_cookie(response, request)
    return response


@router.api_route("/api/test-mode", methods=["GET", "POST"])
def test_mode(request: Request) -> JSONResponse:
    """Arm test traffic. A wrong token is the same 200 with the flag left off."""
    matched = accepts_qa_test_token(
        _settings(request).qa_test_token, request.headers.get("x-test-token", "")
    )
    response = JSONResponse({"is_test": _traffic_is_test(request)})
    if matched:
        _arm_test_cookie(response, request)
    return response


@router.get("/api/transactions")
def transactions(request: Request, language: str = "es") -> dict[str, Any]:
    customer_key = _customer(request)
    customer = request.app.state.bank.get_customer(customer_key)
    if customer is None:
        raise APIError(404, "not_found", "Customer not found")
    lang = _ui_lang(language)
    rows = []
    for tx in request.app.state.bank.get_transactions(customer_key):
        shown = present_time(tx.transaction_ts_utc, customer.tz, customer.customer_country, lang)
        home = tx.customer_country or customer.customer_country
        rows.append(
            {
                "transaction_key": tx.transaction_key,
                "merchant_name": tx.merchant_name,
                "merchant_label": merchant_label(
                    lang, tx.merchant_name, tx.merchant_category, tx.transaction_type
                ),
                "merchant_category": tx.merchant_category,
                "transaction_type": tx.transaction_type,
                "amount": tx.amount,
                "amount_label": money(tx.amount, tx.currency, home),
                "currency": tx.currency,
                "transaction_city": tx.transaction_city,
                "transaction_country": tx.transaction_country,
                "customer_country": home,
                "place": place_label(tx.transaction_city, tx.transaction_country, home, lang),
                "transaction_status": tx.transaction_status,
                "status_label": transaction_status_label(lang, tx.transaction_status),
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
) -> JSONResponse:
    settings = _settings(request)
    customer_key = _customer(request)
    presented_eval = (eval_runner_token or "").strip()
    # A judge token never stamps an eval run, even with a valid runner header.
    judge_bearer = agent_role(settings, _bearer(request)) == "judge"
    judge_header = agent_role(settings, presented_eval) == "judge"
    if judge_bearer or judge_header:
        eval_run_id, case_source = None, None
    else:
        eval_run_id, case_source = accept_eval_fields(
            eval_runner_token,
            settings.eval_runner_token,
            body.eval_run_id,
            body.case_source,
        )
    is_eval = bool(eval_run_id or case_source)
    header_match = accepts_qa_test_token(
        _settings(request).qa_test_token, request.headers.get("x-test-token", "")
    )
    result = request.app.state.engine.open_case(
        customer_key,
        body.transaction_key,
        body.message,
        body.language,
        eval_run_id,
        case_source,
        is_test=False if is_eval else _traffic_is_test(request),
        demo_attack=body.demo_attack,
    )
    response = JSONResponse(result.as_dict())
    if header_match and not is_eval:
        _arm_test_cookie(response, request)
    return response


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
        "is_test": case.get("is_test"),
    }


@router.get("/api/cases/{case_id}/trail")
def case_trail(case_id: str, request: Request, language: str | None = None) -> dict[str, Any]:
    settings = _settings(request)
    role = agent_role(settings, _bearer(request))
    customer_key = ""
    if role is None:
        customer_key = _customer(request)
    case = request.app.state.ops.get_case(case_id)
    if case is None or (role is None and case["customer_key"] != customer_key):
        raise APIError(404, "not_found", "Case not found")
    customer = request.app.state.bank.get_customer(str(case["customer_key"]))
    tz = customer.tz if customer is not None else None
    country = customer.customer_country if customer is not None else case.get("country")
    shown_language = str(case.get("language") or "es")
    if role is not None and language in {"es", "pt"}:
        shown_language = _ui_lang(language)
    t_low, high_value = _thresholds(request)
    steps = build_steps(
        request.app.state.ops.audit_chain(case_id),
        request.app.state.ops.list_events(case_id),
        tz=tz,
        country=None if country is None else str(country),
        language=shown_language,
        t_low=t_low,
        high_value=high_value,
        safe=role is None,
    )
    return {
        "case_id": case_id,
        "scope": "customer" if role is None else "agent",
        "steps": steps,
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
def handoff_queue(request: Request, language: str | None = None) -> dict[str, Any]:
    _agent(request)
    lang = language if language in {"es", "pt"} else None
    audits = {row["case_id"]: row for row in request.app.state.ops.current_audit_cases()}
    items = [
        queue_card(row, audits.get(row["case_id"]), display_language=lang)
        for row in request.app.state.ops.list_handoffs()
    ]
    for item in items:
        _record_console(request, str(item["case_id"]), "list")
    return {"queue": items}


@router.get("/api/handoff/{case_id}")
def handoff_case(case_id: str, request: Request, language: str | None = None) -> dict[str, Any]:
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
    view = packet_view(
        row,
        _audit_for(request, case_id),
        t_low=t_low,
        high_value=high_value,
        display_language=language if language in {"es", "pt"} else None,
    )
    evidence = request.app.state.band_evidence.line(str(view.get("band") or ""))
    if evidence:
        view["band_evidence"] = evidence
    _attach_reply(request, case_id, view)
    _record_console(request, case_id, "open")
    return {
        "handoff": row,
        "events": safe_events,
        "view": view,
    }


def _reply_facts(request: Request, case_id: str) -> dict[str, str]:
    row = request.app.state.ops.get_handoff(case_id)
    if row is None:
        raise APIError(404, "not_found", "Handoff not found")
    packet = HandoffPacket.model_validate(row["packet"])
    customer = request.app.state.engine.bank.get_customer(packet.customer_key)
    country = customer.customer_country if customer is not None else ""
    return fact_sheet(packet, country, _settings(request))


def _attach_reply(request: Request, case_id: str, view: dict[str, Any]) -> None:
    case = request.app.state.ops.get_case(case_id)
    draft = str(case.get("reply_draft") or "") if case else ""
    sent = str(case.get("reply_sent") or "") if case else ""
    view["reply_draft"] = draft
    view["reply_sent"] = sent
    if not draft:
        view["reply_grounded"] = False
        view["reply_unsupported"] = []
        return
    checked = grounded(draft, _reply_facts(request, case_id))
    view["reply_grounded"] = bool(checked["ok"])
    view["reply_unsupported"] = list(checked["unsupported_facts"])


@router.post("/api/handoff/{case_id}/draft-check")
def draft_check(case_id: str, body: ReplyIn, request: Request) -> dict[str, Any]:
    _agent(request)
    checked = grounded(body.text, _reply_facts(request, case_id))
    _record_console(request, case_id, "draft")
    return checked


@router.post("/api/handoff/{case_id}/reply")
def send_reply(case_id: str, body: ReplyIn, request: Request) -> dict[str, Any]:
    _agent(request)
    text = body.text.strip()
    if not text:
        raise APIError(400, "empty_reply", "Reply text is required")
    request.app.state.engine.record_reply_sent(case_id, text, source=_console_source(request))
    checked = grounded(text, _reply_facts(request, case_id))
    return {
        "status": "reply_sent",
        "ok": checked["ok"],
        "unsupported_facts": checked["unsupported_facts"],
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
    _record_console(request, case_id, "resolve")
    return {"status": "resolved"}


def _audit_rows_for_read(
    ops: Any, *, include_eval: bool, include_test: bool
) -> tuple[list[dict[str, Any]], int, int]:
    """Default reads audit_live. Admin include flags read audit_current.

    A missing test schema reads audit_current so metrics and the export stay up.
    """
    current = ops.current_audit_cases()
    if not getattr(ops, "migrations_ok", False):
        return select_cases(
            current,
            include_eval=include_eval,
            include_test=include_test,
            test_ids=set(),
        )
    test_ids = ops.test_case_ids()
    if include_eval or include_test:
        return select_cases(
            current,
            include_eval=include_eval,
            include_test=include_test,
            test_ids=test_ids,
        )
    _, excluded_eval, excluded_test = select_cases(
        current,
        include_eval=False,
        include_test=False,
        test_ids=test_ids,
    )
    return ops.live_audit_cases(), excluded_eval, excluded_test


@router.get("/api/metrics")
def metrics(
    request: Request,
    include_eval: bool = False,
    include_test: bool = False,
    language: str = "",
) -> dict[str, Any]:
    # Public on purpose: aggregates only, no per-customer rows or PII.
    # include_eval and include_test are ignored unless the admin token is present.
    include_eval = _admin_include(request, include_eval)
    include_test = _admin_include(request, include_test)
    ops = request.app.state.ops
    rows, excluded_eval, excluded_test = _audit_rows_for_read(
        ops, include_eval=include_eval, include_test=include_test
    )
    payload = compute_metrics(
        rows,
        ops.current_llm_calls(),
        ops.prices(),
        ops.assumptions(),
        include_eval=include_eval,
        include_test=include_test,
        excluded_eval=excluded_eval,
        excluded_test=excluded_test,
    )
    if language in {"es", "pt"}:
        payload = localize_metrics(payload, language)
        payload["eval_toggle_label"] = str(ui_copy(language)["eval_toggle"])
    payload["trust"] = trust_panel()
    payload["simulator"] = simulator_panel()
    payload["fairness"] = fairness_panel()
    return payload


@router.get("/audit/export")
def export_audit(
    request: Request, include_eval: bool = False, include_test: bool = False
) -> Response:
    _agent(request, admin_only=True)
    include_eval = _admin_include(request, include_eval)
    include_test = _admin_include(request, include_test)
    rows, _, _ = _audit_rows_for_read(
        request.app.state.ops, include_eval=include_eval, include_test=include_test
    )
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
        "is_test",
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
