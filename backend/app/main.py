"""FastAPI application factory and ASGI entry point.

Run from the repository root:
    uvicorn app.main:app --app-dir backend --port 8000

``app`` is built on first access (uvicorn's ``app.main:app`` lookup), not at import time, so importing
this module (tests, scripts) never reads .env or fails on a broken configuration (audit LOW).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from functools import cache
from typing import Any, AsyncIterator

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, check_startup_rules, load_settings
from .errors import register_error_handlers
from .middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware, UnhandledErrorMiddleware
from .openapi_errors import install_contract_openapi
from .routers import advanced, export, health, insights, metadata, core
from .ai.context import ExplanationContextMiddleware
from .ai.service import ExplanationService
from .ai.resolve import ResultRegistry
from .services.rate_limit import report_limiter
from .services.store import DataStore, build_store, verify_store

API_PREFIX = "/api/v1"
logger = logging.getLogger("trendtrace.main")


def _reports_router():
    """PDF routes need ReportLab + matplotlib; if they cannot load, CSV and the rest still work."""
    try:
        from .routers import reports
    except Exception:  # noqa: BLE001 - any import failure of the PDF stack
        logger.exception("PDF report module unavailable; /report will return REPORT_FAILED")
        from .routers import reports_fallback as reports
    return reports.router


def _configure_logging(settings: Settings) -> None:
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None, store: DataStore | None = None) -> FastAPI:
    """``store`` lets tests inject a fake store; normally DATA_MODE selects it once here."""
    settings = settings or load_settings()
    _configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Startup guard: runs before any request is served; a failure stops the app.
        check_startup_rules(settings)
        selected = store if store is not None else build_store(settings)
        verify_store(selected, settings)
        app.state.store = selected
        yield

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=settings.contract_version,
        debug=False,  # never expose tracebacks, in any environment
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.explanations = ExplanationService(settings)
    app.state.results = ResultRegistry()
    app.state.report_limiter = report_limiter()  # POST /report: 2 at once, 10 per client per minute (M1)

    register_error_handlers(app)
    # Order: the last added runs first. Security headers wrap everything; CORS wraps the error handler,
    # so even an unexpected 500 carries CORS headers (audit LOW).
    app.add_middleware(ExplanationContextMiddleware)
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes)
    # In development Vite proxies /api to localhost:8000, so CORS is only a fallback.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.allowed_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        # The browser may read the CSV/PDF file name and the wait time on 429/503 (audit M7).
        expose_headers=["Content-Disposition", "Retry-After"],
    )
    # The 3D landing page ships three.js and country outlines: compress text responses.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(core.router, prefix=API_PREFIX)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(metadata.router, prefix=API_PREFIX)
    app.include_router(advanced.router, prefix=API_PREFIX)
    app.include_router(insights.router, prefix=API_PREFIX)
    app.include_router(export.router, prefix=API_PREFIX)
    app.include_router(_reports_router(), prefix=API_PREFIX)
    install_contract_openapi(app)  # /docs shows {"error": {...}} for every error (audit M3)

    _mount_frontend(app)
    return app


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


def _mount_frontend(app: FastAPI) -> None:
    """Simple no-build frontend: '/' serves index.html, '/static/*' its CSS/JS.

    Only these two paths are added, so unknown /api paths keep the contract NOT_FOUND error.
    """
    index = FRONTEND_DIR / "index.html"
    if not index.is_file():
        return
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="frontend")

    @app.get("/", include_in_schema=False)
    def frontend_index() -> FileResponse:
        return FileResponse(index, media_type="text/html")


@cache
def _default_app() -> FastAPI:
    return create_app()


def __getattr__(name: str) -> Any:
    """``app.main.app`` (uvicorn, Procfile, render.yaml): the default app, built once on first use."""
    if name == "app":
        return _default_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
