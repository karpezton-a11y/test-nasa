"""Collect the same verified result objects the API serves, for one report request.

Validation errors (INVALID_*, PERIOD_TOO_SHORT, INSUFFICIENT_DATA) stop the
request. A requested section whose data does not exist yet becomes an
``Unavailable`` box in the PDF (decision R-3). Nothing is recomputed here.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from ..advanced_schemas import ReportRequest
from ..errors import ApiError
from ..schemas import Period, TrendResult
from ..services.advanced import INDICATORS, anomalies_for, find_region, indicator_for, interaction_for
from ..services.store import DataStore
from ..services.validation import (
    SEASONS, require_choice, require_coverage, require_min_years, resolve_period, slice_series,
)
from .content import ReportContent, Unavailable, VariableSection

INDICATOR_SEASON = {"all": "annual", "JJAS": "JJAS", "OND": "OND"}
T = TypeVar("T")


def _or_unavailable(fetch: Callable[[], T]) -> T | Unavailable:
    try:
        return fetch()
    except ApiError as err:
        if err.code != "DATA_NOT_AVAILABLE":
            raise
        dataset = err.details.get("dataset", "result")
        return Unavailable(f"{dataset} is not available for this selection yet.")


def _for_period(result: T | Unavailable, period: Period, label: str) -> T | Unavailable:
    """Never print a result under dates it was not computed for (store results carry their own period)."""
    if isinstance(result, Unavailable) or result.period == period:
        return result
    return Unavailable(f"{label} exists only for {result.period.start} to {result.period.end}, "
                       f"not for the requested {period.start} to {period.end}.")


def _variable_section(store: DataStore, req: ReportRequest, variable: str, period: Period) -> VariableSection:
    info = next(v for v in store.variables() if v.variable == variable)
    series = _or_unavailable(lambda: store.series(req.region_id, variable, "month"))
    trend = None
    if "trend" in req.include:
        if not isinstance(series, Unavailable):
            require_coverage(series, period, season=req.season)  # same selection as /analyze
        trend = _for_period(_or_unavailable(lambda: store.trend(req.region_id, variable, period, req.season)),
                            period, f"The {info.label} trend")
        if isinstance(trend, TrendResult) and trend.season != req.season:
            trend = Unavailable(f"The {info.label} trend exists only for season {trend.season}, not {req.season}.")
    if not isinstance(series, Unavailable):
        series = slice_series(series, period)
    return VariableSection(variable=variable, label=info.label, unit=info.unit, unit_label=info.unit_label,
                           series=series, trend=trend)


def _indicators(store: DataStore, req: ReportRequest, period: Period) -> tuple:
    if "rainfall" not in req.variables:
        return (("all", Unavailable("Rainfall indicators need the rainfall variable in the report.")),)
    season = INDICATOR_SEASON.get(req.season)
    if season is None:
        return (("all", Unavailable(f"Rainfall indicators exist for annual, JJAS and OND, not {req.season}.")),)
    return tuple((name, _for_period(_or_unavailable(lambda n=name: indicator_for(store, req.region_id, n, season)),
                                    period, f"The {name} indicator"))
                 for name in INDICATORS)


def assemble_report(store: DataStore, req: ReportRequest, *, app_name: str, contract_version: str,
                    generated_at: str, methods_text: str | None = None,
                    limitations_text: tuple[str, ...] | None = None) -> ReportContent:
    region = find_region(store, req.region_id)
    for variable in req.variables:
        require_choice(variable, region.variables, "INVALID_VARIABLE", "variable")
    require_choice(req.season, SEASONS, "INVALID_SEASON", "season")
    period = resolve_period(req.start, req.end, region.period_available)
    require_min_years(period)
    sections = tuple(_variable_section(store, req, v, period) for v in req.variables)
    anomaly_variable = "both" if len(req.variables) == 2 else req.variables[0]
    return ReportContent(
        app_name=app_name, data_status=store.info.data_status, data_version=store.info.data_version,
        contract_version=contract_version, generated_at=generated_at, region=region, period=period,
        season=req.season, include=tuple(req.include), variables=sections,
        anomalies=(_for_period(_or_unavailable(lambda: anomalies_for(store, req.region_id, anomaly_variable,
                                                                       period.start, period.end, False)),
                               period, "The anomaly list")
                   if "anomalies" in req.include else None),
        interaction=(_for_period(_or_unavailable(lambda: interaction_for(store, req.region_id, req.season)),
                                 period, "The interaction analysis")
                     if "interaction" in req.include else None),
        indicators=_indicators(store, req, period) if "indicators" in req.include else None,
        sources=tuple(store.sources()), methods_text=methods_text, limitations_text=limitations_text,
        include_ai_summary=req.include_ai_summary, ai_summary=None,  # set later by hooks.ai_summary_for
    )
