"""Block prompt-injection attempts before they are written into the model context.

The filter is intentionally narrow so ordinary dispute language ("ignore the coffee
charge") still goes through. A blocked turn is not partially processed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_instructions",
        re.compile(
            r"ignore\s+(?:all\s+|any\s+)?(?:previous|prior|above|earlier)\s+"
            r"(?:instructions|prompts|rules|messages)",
            re.IGNORECASE,
        ),
    ),
    (
        "disregard_instructions",
        re.compile(
            r"disregard\s+(?:your|the|all|any)?\s*(?:instructions|rules|prompts|guidelines)",
            re.IGNORECASE,
        ),
    ),
    ("you_are_now", re.compile(r"you\s+are\s+now\b", re.IGNORECASE)),
    (
        "reveal_prompt",
        re.compile(
            r"(?:reveal|show|print|repeat)\s+(?:me\s+)?(?:your\s+)?(?:system\s+)?(?:prompt|instructions)",
            re.IGNORECASE,
        ),
    ),
    ("forget_rules", re.compile(r"forget\s+(?:everything|all)\s+(?:you|your)", re.IGNORECASE)),
    ("new_instructions", re.compile(r"\b(?:new|updated)\s+instructions\b", re.IGNORECASE)),
    ("jailbreak", re.compile(r"\bjailbreak\b", re.IGNORECASE)),
    (
        "skip_tools",
        re.compile(r"do\s+not\s+(?:use|call)\s+(?:the\s+)?tools", re.IGNORECASE),
    ),
    (
        "override_policy",
        re.compile(r"override\s+(?:the\s+)?(?:policy|rules|safety|guardrails)", re.IGNORECASE),
    ),
    ("system_role", re.compile(r"(?:^|\n)\s*system\s*:\s*", re.IGNORECASE)),
    (
        "tool_spoof",
        re.compile(r"<\s*/?\s*(?:tool_call|function_call|system)\s*>", re.IGNORECASE),
    ),
)


@dataclass(frozen=True)
class InjectionResult:
    blocked: bool
    rule: str | None = None


def detect_injection(text: str) -> InjectionResult:
    for name, pattern in _RULES:
        if pattern.search(text):
            return InjectionResult(blocked=True, rule=name)
    return InjectionResult(blocked=False)
