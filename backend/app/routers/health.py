"""GET /api/v1/health: dependency-free liveness check."""

from __future__ import annotations

from importlib import metadata

from fastapi import APIRouter, Depends, Request

from ..openapi_errors import error_responses
from ..schemas import Envelope, HealthResult
from ..services.store import DataStore, get_store
from .common import envelope

router = APIRouter(tags=["meta"])


def trendlib_version() -> str | None:
    """Installed trendlib version, or the bundled analysis/trendlib version; None if neither imports."""
    try:
        return metadata.version("trendlib")
    except metadata.PackageNotFoundError:
        from ..services.science import trendlib_version as bundled
        return bundled()


@router.get("/health", response_model=Envelope[HealthResult], responses=error_responses())
def get_health(request: Request, store: DataStore = Depends(get_store)) -> Envelope[HealthResult]:
    settings = request.app.state.settings
    info = store.info  # in-memory provenance; no file reads here
    data_status, data_version = info.data_status, info.data_version
    result = HealthResult(
        status="ok",
        data_status=data_status,
        data_version=data_version,
        trendlib_version=trendlib_version(),
        ai_available=settings.llm_api_key_set,  # configuration only; the provider is not contacted
    )
    return envelope(request, result, store=store)
