"""Harness entry point. The check itself ships inside the app image."""

from app.guardrails.draft_check import grounded

__all__ = ["grounded"]
