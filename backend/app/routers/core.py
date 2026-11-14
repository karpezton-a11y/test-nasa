"""Adrian's core routes in the existing app and existing envelope/error system."""
from fastapi import APIRouter, Depends, Query, Request

from ..core_schemas import AnalyzeRequest, CompareRequest, CompareResult, ExplainRequest, Explanation
from ..schemas import Envelope, TimeSeries, TrendResult
from ..services.core import analyze_for, compare_for, series_for
from ..services.store import DataStore, get_store
from ..ai.resolve import resolve
from ..openapi_errors import error_responses
from .common import envelope

router = APIRouter(tags=["science"])


@router.get("/timeseries", response_model=Envelope[TimeSeries], responses=error_responses("INVALID_REGION", "INVALID_VARIABLE", "INVALID_PERIOD", "VALIDATION_ERROR", "DATA_NOT_AVAILABLE"))
def timeseries(request: Request, region_id: str = Query(..., max_length=32),
               variable: str = Query(..., max_length=32), frequency: str = Query("month", max_length=8),
               start: str | None = Query(None, max_length=7), end: str | None = Query(None, max_length=7),
               source_id: str | None = Query(None, max_length=80), store: DataStore = Depends(get_store)):
    return envelope(request, series_for(store, region_id, variable, frequency, start, end, source_id))


@router.post("/analyze", response_model=Envelope[TrendResult], responses=error_responses("INVALID_REGION", "INVALID_VARIABLE", "INVALID_SEASON", "INVALID_PERIOD", "PERIOD_TOO_SHORT", "INSUFFICIENT_DATA", "VALIDATION_ERROR", "DATA_NOT_AVAILABLE"))
def analyze(request: Request, body: AnalyzeRequest, store: DataStore = Depends(get_store)):
    result = analyze_for(store, body)
    request.app.state.results.remember("trend", result)
    return envelope(request, result)


@router.post("/compare", response_model=Envelope[CompareResult], response_model_exclude_unset=True, responses=error_responses("INVALID_REGION", "INVALID_VARIABLE", "INVALID_SEASON", "INVALID_PERIOD", "PERIOD_TOO_SHORT", "INSUFFICIENT_DATA", "VALIDATION_ERROR", "DATA_NOT_AVAILABLE"))
def compare(request: Request, body: CompareRequest, store: DataStore = Depends(get_store)):
    result = compare_for(store, body)
    for trend in result.results: request.app.state.results.remember("trend", trend)
    return envelope(request, result)


@router.post("/explain", response_model=Envelope[Explanation], responses=error_responses("VALIDATION_ERROR", "INVALID_VARIABLE", "INVALID_PERIOD", "PERIOD_TOO_SHORT", "INSUFFICIENT_DATA", "DATA_NOT_AVAILABLE", "RATE_LIMITED", "AI_UNAVAILABLE"))
def explain(request: Request, body: ExplainRequest, store: DataStore = Depends(get_store)):
    service = request.app.state.explanations
    # Keep the admission slot until generation completes, including provider I/O.
    with service.limiter.slot(request.client.host if request.client else "unknown"):
        results = resolve(body, store, request.app.state.results)
        return envelope(request, service.explain(results, data_status=store.info.data_status,
                                                data_version=store.info.data_version))
