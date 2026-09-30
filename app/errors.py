"""HTTP errors that do not echo exception text back to the client."""

from __future__ import annotations


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class LLMError(Exception):
    """The live model call failed. Mock mode does not raise this for business rules."""
