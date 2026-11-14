"""Request validation + selection for the advanced results (contract G, H, J).

One code path for the API routers, the PDF report and the CSV export, so every
consumer gets the same object for the same request. Steps: validate IDs/period
-> ask the store -> check the returned object really answers this request.
No statistics here: values pass through unchanged, and a missing file is
DATA_NOT_AVAILABLE from the store (never a mock fallback).
"""

from __future__ import annotations

import logging
from typing import Any, get_args

from ..advanced_schemas import (
    AnomalyBothResult, AnomalyResult, IndicatorName, IndicatorResult, IndicatorSeason, InteractionResult,
)
from ..schemas import Region
from .store import DataStore
from .validation import SEASONS, require_choice, resolve_period

logger = logging.getLogger("trendtrace.advanced")

BOTH = "both"
INTERACTION_SEASONS: tuple[str, ...] = SEASONS  # contract H: all | JF | MAM | JJAS | OND
INDICATORS: tuple[str, ...] = get_args(IndicatorName)
INDICATOR_SEASONS: tuple[str, ...] = get_args(IndicatorSeason)


class ResultMismatch(RuntimeError):
    """The store returned a result for a different request: a bug, never served (-> INTERNAL_ERROR)."""


def find_region(store: DataStore, region_id: str) -> Region:
    regions = {r.region_id: r for r in store.regions().regions}
    require_choice(region_id, sorted(regions), "INVALID_REGION", "region_id")
    return regions[region_id]


def anomaly_variables(region: Region) -> list[str]:
    """Variables the region offers, plus ``both`` when it has rainfall and AOD."""
    extra = [BOTH] if {"rainfall", "aod"} <= set(region.variables) else []
    return [*region.variables, *extra]


def _expect(kind: str, actual: dict[str, Any], wanted: dict[str, Any]) -> None:
    if actual != wanted:
        logger.error("Store returned a %s result for %s instead of %s", kind, actual, wanted)
        raise ResultMismatch(f"store returned a {kind} result for a different request")


def anomalies_for(store: DataStore, region_id: str, variable: str, start: str | None, end: str | None,
                  detrended: bool) -> AnomalyResult | AnomalyBothResult:
    region = find_region(store, region_id)
    require_choice(variable, anomaly_variables(region), "INVALID_VARIABLE", "variable")
    period = resolve_period(start, end, region.period_available)
    result = store.anomalies(region_id, variable, period, detrended)
    is_detrended = result.detrended if isinstance(result, AnomalyBothResult) else result.baseline.detrended
    _expect("anomaly",
            {"region_id": result.region_id, "variable": result.variable, "period": result.period,
             "detrended": is_detrended},
            {"region_id": region_id, "variable": variable, "period": period, "detrended": detrended})
    return result


def interaction_for(store: DataStore, region_id: str, season: str) -> InteractionResult:
    find_region(store, region_id)
    require_choice(season, INTERACTION_SEASONS, "INVALID_SEASON", "season")
    result = store.interaction(region_id, season)
    _expect("interaction", {"region_id": result.region_id, "season": result.season},
            {"region_id": region_id, "season": season})
    return result


def indicator_for(store: DataStore, region_id: str, indicator: str, season: str) -> IndicatorResult:
    find_region(store, region_id)
    require_choice(indicator, INDICATORS, "INVALID_INDICATOR", "indicator")
    require_choice(season, INDICATOR_SEASONS, "INVALID_SEASON", "season")
    result = store.indicator(region_id, indicator, season)
    _expect("indicator", {"region_id": result.region_id, "indicator": result.indicator, "season": result.season},
            {"region_id": region_id, "indicator": indicator, "season": season})
    return result
