"""Advanced result endpoints (contract G, H, J): /anomalies, /interaction, /rainfall/indicators.

Thin routers: validation and selection live in services/advanced.py (shared with
the PDF and CSV), the store serves stored or trendlib-computed results, and the
values are returned unchanged inside the envelope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..advanced_schemas import AnomalyBothResult, AnomalyResult, IndicatorResult, InteractionResult
from ..openapi_errors import error_responses
from ..schemas import Envelope
from ..services.advanced import anomalies_for, indicator_for, interaction_for
from ..services.store import DataStore, get_store
from .common import envelope

router = APIRouter(tags=["advanced"])


@router.get("/anomalies", response_model=Envelope[AnomalyResult | AnomalyBothResult],
            responses=error_responses("INVALID_REGION", "INVALID_VARIABLE", "INVALID_PERIOD", "VALIDATION_ERROR",
                                      "DATA_NOT_AVAILABLE"))
def get_anomalies(
    request: Request,
    region_id: str = Query(...),
    variable: str = Query(..., description="rainfall | aod | both"),
    start: str | None = Query(None, description="YYYY-MM; default: start of available data"),
    end: str | None = Query(None, description="YYYY-MM; default: end of available data"),
    detrended: bool = Query(False),
    store: DataStore = Depends(get_store),
) -> Envelope[AnomalyResult | AnomalyBothResult]:
    return envelope(request, anomalies_for(store, region_id, variable, start, end, detrended), store=store)


@router.get("/interaction", response_model=Envelope[InteractionResult],
            responses=error_responses("INVALID_REGION", "INVALID_SEASON", "VALIDATION_ERROR", "DATA_NOT_AVAILABLE"))
def get_interaction(
    request: Request,
    region_id: str = Query(...),
    season: str = Query(..., description="all | JF | MAM | JJAS | OND"),
    store: DataStore = Depends(get_store),
) -> Envelope[InteractionResult]:
    return envelope(request, interaction_for(store, region_id, season), store=store)


@router.get("/rainfall/indicators", response_model=Envelope[IndicatorResult],
            responses=error_responses("INVALID_REGION", "INVALID_INDICATOR", "INVALID_SEASON", "VALIDATION_ERROR",
                                      "DATA_NOT_AVAILABLE"))
def get_rainfall_indicator(
    request: Request,
    region_id: str = Query(...),
    indicator: str = Query(..., description="heavy_rain_share | longest_dry_spell | rx5day"),
    season: str = Query(..., description="annual | JJAS | OND"),
    store: DataStore = Depends(get_store),
) -> Envelope[IndicatorResult]:
    return envelope(request, indicator_for(store, region_id, indicator, season), store=store)
