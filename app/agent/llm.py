"""One OpenAI-compatible chat completion with tools. No retries: the agent falls back."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import Settings


@dataclass
class LLMReply:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    model: str = ""


class ChatModel(Protocol):
    def __call__(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], timeout: float
    ) -> LLMReply: ...


class LLMError(RuntimeError):
    """Any model failure. The caller falls back to the guided flow."""


def openai_chat(settings: Settings) -> ChatModel:
    provider = settings.resolved_llm_provider()
    if provider == "openrouter":
        url = settings.openrouter_base_url.rstrip("/") + "/chat/completions"
        key = settings.openrouter_api_key
        model = settings.openrouter_model
    else:
        base = settings.openai_base_url.strip() or "https://api.openai.com/v1"
        url = base.rstrip("/") + "/chat/completions"
        key = settings.openai_api_key
        model = settings.openai_model

    def call(
        messages: list[dict[str, Any]], tools: list[dict[str, Any]], timeout: float
    ) -> LLMReply:
        if provider not in {"openai", "openrouter"} or not key.strip():
            raise LLMError("no model configured")
        body = json.dumps(
            {
                "model": model,
                "temperature": 0,
                "max_tokens": 300,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "parallel_tool_calls": False,
            }
        ).encode()
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=max(timeout, 0.5)) as response:
                payload: dict[str, Any] = json.loads(response.read().decode())
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise LLMError(type(exc).__name__) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise LLMError("no choices")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise LLMError("no message")
        raw_usage = payload.get("usage")
        usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
        calls = []
        for raw in message.get("tool_calls") or []:
            function = raw.get("function") if isinstance(raw, dict) else None
            if not isinstance(function, dict):
                continue
            calls.append(
                {
                    "id": str(raw.get("id") or ""),
                    "name": str(function.get("name") or ""),
                    "arguments": str(function.get("arguments") or "{}"),
                }
            )
        content = message.get("content")
        return LLMReply(
            content=content.strip() if isinstance(content, str) else "",
            tool_calls=calls,
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            latency_ms=latency_ms,
            model=str(payload.get("model") or model),
        )

    return call
