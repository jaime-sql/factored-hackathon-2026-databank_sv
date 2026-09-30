"""Logging with the same PII redactor used before text reaches the model."""

from __future__ import annotations

import logging

from app.guardrails.pii import redact


class RedactFilter(logging.Filter):
    """Rewrite log messages and string arguments before they are formatted."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, dict):
            record.args = {
                key: redact(value) if isinstance(value, str) else value
                for key, value in record.args.items()
            }
        elif isinstance(record.args, tuple):
            record.args = tuple(
                redact(value) if isinstance(value, str) else value for value in record.args
            )
        return True


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))
    redact_filter = RedactFilter()
    root = logging.getLogger()
    root.addFilter(redact_filter)
    for handler in root.handlers:
        handler.addFilter(redact_filter)
    logging.getLogger("app").addFilter(redact_filter)
