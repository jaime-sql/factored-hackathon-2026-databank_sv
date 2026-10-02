"""Agent-console audit decisions.

These rows are tips, so they stay in audit_live. Routing, the packet, and the
KPI totals skip them and keep the customer decision.
"""

from __future__ import annotations

CONSOLE_ACTIONS = ("list", "open", "resolve", "draft")
CONSOLE_DECISIONS = frozenset(f"console_{action}" for action in CONSOLE_ACTIONS)


def is_console_decision(decision: object) -> bool:
    return decision in CONSOLE_DECISIONS
