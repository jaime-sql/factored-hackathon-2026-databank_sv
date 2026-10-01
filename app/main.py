"""Harbor Desk application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.band_evidence import BandEvidenceSource
from app.bank.fixture import PERSONAS, init_bank
from app.bank.repository import SQLBankRepository
from app.cases.engine import Engine
from app.config import Settings, get_settings
from app.errors import APIError
from app.guardrails.pii import set_known_names
from app.i18n import write_catalog_script
from app.logging_config import configure_logging
from app.ops.store import OpsStore
from app.paths import project_root
from app.thresholds_loader import ThresholdSource
from app.triage_model import LightGBMTriage


def create_app(settings: Settings | None = None) -> FastAPI:
    active = settings or get_settings()
    configure_logging(active.log_level)
    set_known_names(["Ana", "Camilo", "María", "Maria", "Teo", *[row["label"] for row in PERSONAS]])

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        root = project_root()
        threshold_path = (
            Path(active.thresholds_path)
            if active.thresholds_path
            else (root / "triage" / "artifacts" / "thresholds.json")
        )
        if active.database_url.strip():
            bank = SQLBankRepository("postgres", dsn=active.database_url)
            ops = OpsStore("postgres", dsn=active.database_url)
        else:
            bank_path = active.bank_db_path or str(root / "data" / "bank.sqlite")
            ops_path = active.ops_db_path or str(root / "data" / "ops.sqlite")
            Path(bank_path).parent.mkdir(parents=True, exist_ok=True)
            Path(ops_path).parent.mkdir(parents=True, exist_ok=True)
            init_bank(bank_path)
            bank = SQLBankRepository("sqlite", path=bank_path)
            ops = OpsStore("sqlite", path=ops_path)
        app.state.settings = active
        app.state.bank = bank
        app.state.ops = ops
        app.state.thresholds = ThresholdSource(threshold_path)
        app.state.band_evidence = BandEvidenceSource(
            root / "triage" / "artifacts" / "band_evidence.json"
        )
        app.state.triage = LightGBMTriage()
        app.state.engine = Engine(bank, ops, app.state.thresholds, active, app.state.triage)
        yield

    app = FastAPI(title="Harbor Desk", lifespan=lifespan)
    app.state.settings = active

    @app.exception_handler(APIError)
    async def on_api_error(_: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content={"error": exc.code, "message": exc.message}
        )

    app.include_router(router)
    write_catalog_script()
    static = project_root() / "static"
    if static.exists():
        app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(static / "favicon.ico", media_type="image/x-icon")

    @app.get("/")
    def desk() -> FileResponse:
        return FileResponse(static / "index.html")

    @app.get("/agent")
    def agent() -> FileResponse:
        return FileResponse(static / "agent.html")

    @app.get("/metrics")
    def metrics_page() -> FileResponse:
        return FileResponse(static / "metrics.html")

    return app


app = create_app()
