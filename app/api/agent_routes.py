"""AI agent intake endpoints. 404 unless AGENT_ENABLED is on."""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.agent.copy import agent_catalog
from app.agent.loop import AgentRequest, AgentRunner
from app.api.routes import _customer, _schedule_drafts, _settings, _traffic_is_test
from app.auth.session import agent_role
from app.errors import APIError
from app.eval_access import accept_eval_fields

agent_router = APIRouter()


class Turn(BaseModel):
    role: str = Field(default="user", max_length=16)
    text: str = Field(default="", max_length=1000)


class AgentMessageIn(BaseModel):
    message: str = Field(default="", max_length=1000)
    language: str | None = None
    conversation_id: str | None = Field(default=None, max_length=64)
    transaction_key: str | None = Field(default=None, max_length=64)
    history: list[Turn] = Field(default_factory=list, max_length=12)
    stream: bool = False
    eval_run_id: str | None = None
    case_source: str | None = None
    # Eval runner only (valid EVAL_RUNNER_TOKEN and eval_run_id): act as this customer.
    customer_key: str | None = Field(default=None, max_length=64)


def _enabled(request: Request) -> bool:
    return bool(_settings(request).agent_enabled)


@agent_router.get("/api/agent/config")
def agent_config(request: Request) -> dict[str, Any]:
    enabled = _enabled(request)
    return {"enabled": enabled, "copy": agent_catalog() if enabled else {}}


@agent_router.post("/api/agent/message", response_model=None)
def agent_message(
    body: AgentMessageIn,
    request: Request,
    background: BackgroundTasks,
    eval_runner_token: str | None = Header(default=None, alias="EVAL_RUNNER_TOKEN"),
) -> JSONResponse | StreamingResponse:
    if not _enabled(request):
        raise APIError(404, "not_found", "Not found")
    settings = _settings(request)
    presented = (eval_runner_token or "").strip()
    if agent_role(settings, presented) == "judge" and (body.eval_run_id or body.case_source):
        raise APIError(403, "eval_fields_forbidden", "A judge token cannot set eval fields")
    eval_run_id, case_source = accept_eval_fields(
        eval_runner_token, settings.eval_runner_token, body.eval_run_id, body.case_source
    )
    is_eval = bool(eval_run_id or case_source)
    engine = request.app.state.engine
    if body.customer_key and is_eval:
        if engine.bank.get_customer(body.customer_key) is None:
            raise APIError(404, "not_found", "Customer not found")
        customer_key = body.customer_key
    elif body.customer_key:
        raise APIError(403, "forbidden", "customer_key needs the eval runner token")
    else:
        customer_key = _customer(request)
    runner = AgentRunner(
        engine,
        request.app.state.agent_model,
        timeout_seconds=settings.agent_timeout_seconds,
        secret=settings.session_secret,
    )
    agent_request = AgentRequest(
        customer_key=customer_key,
        message=body.message,
        language=body.language,
        conversation_id=body.conversation_id,
        transaction_key=body.transaction_key,
        history=[turn.model_dump() for turn in body.history],
        is_test=False if is_eval else _traffic_is_test(request),
        force_test=settings.force_test_cases,
        eval_run_id=eval_run_id,
        case_source=case_source,
    )
    if not body.stream:
        with engine.deferred_drafts() as pending:
            result = runner.run(agent_request)
        _schedule_drafts(background, engine, pending)
        return JSONResponse(result)

    events: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def work() -> None:
        pending: list[str] = []
        try:
            with engine.deferred_drafts() as pending:
                result = runner.run(agent_request, events.put)
            events.put({"type": "final", "result": result})
        except Exception:
            events.put({"type": "error"})
        finally:
            events.put(None)
        # A draft that fails here is written on the first console open.
        for case_id in pending:
            engine.ensure_reply_draft(case_id)

    def lines() -> Iterator[bytes]:
        threading.Thread(target=work, daemon=True).start()
        while True:
            event = events.get()
            if event is None:
                break
            yield (json.dumps(event, ensure_ascii=False) + "\n").encode()

    return StreamingResponse(
        lines(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
