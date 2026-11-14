"""Discovery, demos and insight routes (additive to contract A-J).

GET  /catalog              variable catalogue with plain-language definitions
GET  /discover/questions   guided question flow
POST /discover             ranked variable suggestions with reasons
GET  /demos                watchable walkthroughs
GET  /research/series      real annual NASA-derived series bundled from Group 3's research
GET  /research/series/{id} one series
POST /analyze/detail       trend + chart fit/band + change point + years-to-detect + plain language
POST /analyze/series       analyse a research series, an inline series, or a Giovanni CSV
GET  /scan                 every region x variable, FDR-corrected: what/where/how much/significant
"""
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from ..core_schemas import AnalyzeRequest
from ..insights_schemas import DetailResult, DiscoverRequest, SeriesRequest
from ..openapi_errors import error_responses
from ..schemas import Envelope
from ..services import catalog, demos, insights
from ..services.store import DataStore, get_store
from .common import envelope

router = APIRouter(tags=["discovery and insights"])
TREND_ERRORS = ("INVALID_REGION", "INVALID_VARIABLE", "INVALID_SEASON", "INVALID_PERIOD", "PERIOD_TOO_SHORT",
                "INSUFFICIENT_DATA", "VALIDATION_ERROR", "DATA_NOT_AVAILABLE")


@router.get("/catalog", response_model=Envelope[dict[str, Any]], responses=error_responses())
def get_catalog(request: Request, store: DataStore = Depends(get_store)):
    return envelope(request, catalog.catalog_for(store), store=store)


@router.get("/discover/questions", response_model=Envelope[dict[str, Any]], responses=error_responses())
def get_questions(request: Request, store: DataStore = Depends(get_store)):
    return envelope(request, catalog.questions_for(store), store=store)


@router.post("/discover", response_model=Envelope[dict[str, Any]],
             responses=error_responses("VALIDATION_ERROR", "INVALID_REGION"))
def post_discover(request: Request, body: DiscoverRequest, store: DataStore = Depends(get_store)):
    return envelope(request, catalog.discover(store, theme=body.theme, place_type=body.place_type,
                                              question=body.question, region_id=body.region_id, limit=body.limit),
                    store=store)


@router.get("/demos", response_model=Envelope[list[dict[str, Any]]], responses=error_responses())
def get_demos(request: Request, store: DataStore = Depends(get_store)):
    return envelope(request, demos.demos(), store=store)


@router.get("/research/series", response_model=Envelope[dict[str, Any]], responses=error_responses())
def get_research(request: Request, store: DataStore = Depends(get_store)):
    return envelope(request, insights.research_list(), store=store)


@router.get("/research/series/{research_id}", response_model=Envelope[dict[str, Any]],
            responses=error_responses("DATA_NOT_AVAILABLE"))
def get_research_series(request: Request, research_id: str, store: DataStore = Depends(get_store)):
    return envelope(request, insights.research_series(research_id[:64]), store=store)


@router.post("/analyze/detail", response_model=Envelope[DetailResult], responses=error_responses(*TREND_ERRORS))
def post_detail(request: Request, body: AnalyzeRequest, store: DataStore = Depends(get_store)):
    result = insights.detail_for(store, body)
    request.app.state.results.remember("trend", result["trend"])
    return envelope(request, DetailResult(**result), store=store)


@router.post("/analyze/series", response_model=Envelope[dict[str, Any]],
             responses=error_responses("INSUFFICIENT_DATA", "VALIDATION_ERROR", "DATA_NOT_AVAILABLE"))
def post_series(request: Request, body: SeriesRequest, store: DataStore = Depends(get_store)):
    return envelope(request, insights.analyze_series(body), store=store)


@router.get("/scan", response_model=Envelope[dict[str, Any]],
            responses=error_responses("INVALID_SEASON", "INVALID_VARIABLE", "VALIDATION_ERROR", "DATA_NOT_AVAILABLE"))
def get_scan(request: Request, season: str = Query("all", max_length=8),
             variable: list[str] | None = Query(None, max_length=8),
             alpha: float = Query(0.05), start: str | None = Query(None, max_length=7),
             end: str | None = Query(None, max_length=7), store: DataStore = Depends(get_store)):
    from ..errors import api_error
    if alpha not in (0.01, 0.05, 0.10):
        raise api_error("VALIDATION_ERROR", "alpha must be 0.01, 0.05 or 0.10.", {"param": "alpha"})
    return envelope(request, insights.scan_for(store, variables=variable, season=season, alpha=alpha,
                                               start=start, end=end), store=store)
