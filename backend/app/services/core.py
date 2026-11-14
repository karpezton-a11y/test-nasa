"""Core selection and contract checks shared by core routers and ID resolution."""
from __future__ import annotations

from ..core_schemas import AnalyzeRequest, CompareRequest, CompareResult, CompareSummary
from ..errors import api_error
from ..schemas import Period, TimeSeries, TrendResult
from .advanced import find_region, interaction_for
from .science import compute_trend, trendlib_available
from .validation import (FREQUENCIES, SEASONS, require_choice, require_daily_limit,
                         require_min_years, require_coverage, resolve_period, slice_series)

MOCK_LIMITATION = "MOCK series: statistics are computed on illustrative data, not NASA observations."


def series_for(store, region_id, variable, frequency="month", start=None, end=None, source_id=None) -> TimeSeries:
    region = find_region(store, region_id)
    require_choice(variable, region.variables, "INVALID_VARIABLE", "variable")
    require_choice(frequency, FREQUENCIES, "VALIDATION_ERROR", "frequency")
    period = resolve_period(start, end, region.period_available)
    if frequency == "day": require_daily_limit(period)
    if source_id is not None:
        registered = {s.source_id for s in store.sources()}
        allowed = next(v.sources for v in store.variables() if v.variable == variable)
        if source_id not in registered or source_id not in allowed:
            raise api_error("VALIDATION_ERROR", "Unknown source for this variable.", {"param": "source_id"})
        lookup = getattr(store, "series_for_source", None)
        series = lookup(region_id, variable, frequency, source_id) if callable(lookup) else store.series(region_id, variable, frequency)
        if series.source_id != source_id:
            raise api_error("DATA_NOT_AVAILABLE", "That source is not available for this selection.", {"dataset": "timeseries", "source_id": source_id})
    else:
        series = store.series(region_id, variable, frequency)
    if (series.region_id, series.variable, series.frequency) != (region_id, variable, frequency):
        raise RuntimeError("Store returned a different time series")
    return slice_series(series, period)


def analyze_for(store, req: AnalyzeRequest) -> TrendResult:
    region = find_region(store, req.region_id)
    require_choice(req.variable, region.variables, "INVALID_VARIABLE", "variable")
    require_choice(req.season, SEASONS, "INVALID_SEASON", "season")
    available = region.period_available
    if req.start is None or req.end is None:
        # A region can hold variables with different records (e.g. OMI from 2004, GPM from 2000):
        # an omitted bound defaults to this variable's own observed span, not the region's widest span.
        full = series_for(store, req.region_id, req.variable)
        observed = [p.date.strftime("%Y-%m") for p in full.points if p.value is not None]
        if observed:
            available = Period(start=max(available.start, observed[0]), end=min(available.end, observed[-1]))
    period = resolve_period(available.start if req.start is None else req.start,
                            available.end if req.end is None else req.end, region.period_available)
    require_min_years(period)
    series = series_for(store, req.region_id, req.variable, start=period.start, end=period.end)
    require_coverage(series, period, season=req.season)
    if store.info.data_status == "mock":
        if trendlib_available():
            # The real statistics run on the labelled mock series, so every season, period and
            # alpha works and the reported slope always matches the plotted series.
            result = compute_trend(series, period, req.season, alpha=req.options.alpha,
                                   exclude_low_coverage=req.options.exclude_low_coverage)
            return result.model_copy(update={"limitations": [MOCK_LIMITATION, *result.limitations]})
        if req.options.exclude_low_coverage:
            raise api_error("DATA_NOT_AVAILABLE", "No fixture exists for this sensitivity selection.", {"dataset": "trend_options"})
        # Without trendlib only the stored fixtures exist; the fixture must match alpha.
        return compute_trend(series, period, req.season, alpha=req.options.alpha,
                             mock_lookup=lambda: store.trend(req.region_id, req.variable, period, req.season))
    analysis = getattr(store, "analysis", None)
    if callable(analysis):
        return analysis(req.region_id, req.variable, period, req.season, alpha=req.options.alpha,
                        exclude_low_coverage=req.options.exclude_low_coverage)
    return compute_trend(series, period, req.season, alpha=req.options.alpha,
                         exclude_low_coverage=req.options.exclude_low_coverage)


def compare_for(store, req: CompareRequest) -> CompareResult:
    association = None
    if req.mode == "regions":
        regions = [find_region(store, r) for r in req.region_ids]
        # [PROVISIONAL] CORE-01: omitted dates use common availability, never compare different windows.
        available = Period(start=max(r.period_available.start for r in regions),
                           end=min(r.period_available.end for r in regions)) if max(r.period_available.start for r in regions) <= min(r.period_available.end for r in regions) else None
        if available is None:
            raise api_error("DATA_NOT_AVAILABLE", "These regions have no common period.", {"dataset": "comparison"})
        period = resolve_period(req.start, req.end, available)
        selections = [(r.region_id, req.variable) for r in regions]
    else:
        region = find_region(store, req.region_id)
        period = resolve_period(req.start, req.end, region.period_available)
        selections = [(req.region_id, v) for v in req.variables]
    results = [analyze_for(store, AnalyzeRequest(region_id=r, variable=v, start=period.start,
                                                end=period.end, season=req.season)) for r, v in selections]
    if req.mode == "variables":
        interaction = interaction_for(store, req.region_id, req.season)
        if interaction.period != period:
            raise api_error("DATA_NOT_AVAILABLE", "Monthly association is not available for the requested period.",
                            {"dataset": "interaction_summary", "available": interaction.period.model_dump()})
        association = interaction.monthly_association
    same = len({r.direction for r in results}) == 1 if all(r.significant for r in results) else None
    note = ("All compared trends are statistically significant." if same is not None else
            "At least one trend is not statistically significant; no shared direction is asserted.")
    extra = {"monthly_association": association} if req.mode == "variables" else {}
    return CompareResult(mode=req.mode, results=results, summary=CompareSummary(same_direction=same, note=note), **extra)
