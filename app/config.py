"""Environment-backed settings. Empty values keep the local demo defaults."""

from __future__ import annotations

from functools import lru_cache
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SESSION_SECRET = "dev-insecure-session-secret"
DEV_AGENT_TOKEN = "demo-agent-local"
PROMPT_VERSION = "prompt_v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "local"
    port: int = 8091
    log_level: str = "INFO"

    llm_provider: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = ""
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_timeout_seconds: float = Field(default=20, ge=1, le=60)
    llm_max_retries: int = Field(default=2, ge=0, le=4)

    database_url: str = ""
    ops_db_path: str = ""
    bank_db_path: str = ""
    thresholds_path: str = ""

    session_secret: str = DEV_SESSION_SECRET
    session_ttl_hours: int = Field(default=12, ge=1, le=168)

    clerk_secret_key: str = ""
    clerk_publishable_key: str = ""
    demo_agent_token: str = DEV_AGENT_TOKEN
    demo_agent_email: str = "agent@harbor-bank.example"
    eval_runner_token: str = ""
    prompt_version: str = PROMPT_VERSION

    @property
    def clerk_configured(self) -> bool:
        return bool(self.clerk_secret_key.strip() and self.clerk_publishable_key.strip())

    def resolved_llm_provider(self) -> str:
        explicit = self.llm_provider.strip().lower()
        if explicit:
            if explicit not in {"template", "mock", "openai", "openrouter"}:
                raise ValueError("LLM_PROVIDER must be template, mock, openai, or openrouter")
            if explicit == "mock":
                return "template"
            return explicit
        if self.openai_api_key.strip():
            return "openai"
        if self.openrouter_api_key.strip():
            return "openrouter"
        return "template"

    @model_validator(mode="after")
    def normalize(self) -> Self:
        if not self.session_secret.strip():
            self.session_secret = DEV_SESSION_SECRET
        if not self.demo_agent_token.strip():
            self.demo_agent_token = DEV_AGENT_TOKEN
        provider = self.llm_provider.strip().lower()
        if provider and provider not in {"template", "mock", "openai", "openrouter"}:
            raise ValueError("LLM_PROVIDER must be template, mock, openai, or openrouter")
        self.llm_provider = provider
        if self.environment == "production":
            missing: list[str] = []
            if not self.database_url.strip():
                missing.append("DATABASE_URL")
            if self.session_secret == DEV_SESSION_SECRET or len(self.session_secret) < 32:
                missing.append("SESSION_SECRET")
            clerk_ok = self.clerk_configured
            token_ok = self.demo_agent_token != DEV_AGENT_TOKEN and len(self.demo_agent_token) >= 16
            if not clerk_ok and not token_ok:
                missing.append("CLERK keys or a non-default DEMO_AGENT_TOKEN")
            if missing:
                raise ValueError("production requires " + ", ".join(missing))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
