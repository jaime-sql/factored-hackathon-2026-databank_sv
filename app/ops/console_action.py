"""Agent-console audit decisions.

These rows are tips, so they stay in audit_live. Routing, the packet, and the
KPI totals skip them and keep the customer decision.
"""

from __future__ import annotations

CONSOLE_ACTIONS = ("open", "resolve", "draft")
# Older builds wrote console_list. Those rows stay out of routing and KPI totals.
CONSOLE_DECISIONS = frozenset(
    {"console_list", *(f"console_{action}" for action in CONSOLE_ACTIONS)}
)


def is_console_decision(decision: object) -> bool:
    return decision in CONSOLE_DECISIONS
