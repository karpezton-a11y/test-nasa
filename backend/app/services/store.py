"""Data-store seam: one interface, selected once at startup by DATA_MODE.

Routers only ever call ``get_store(request)`` and the ``DataStore`` methods;
they never branch on mock/real. Member 1's real loader implements the same
protocol in ``app/services/real_store.py`` (function ``create_store(settings)``).
"""

from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from fastapi import Request
from pydantic import TypeAdapter

from ..advanced_schemas import AnomalyBothResult, AnomalyResult, IndicatorResult, InteractionResult
from ..config import ConfigError, Settings
from ..errors import api_error
from ..schemas import Envelope, Period, RegionsResult, SourceInfo, TimeSeries, TrendResult, VariableInfo

logger = logging.getLogger("trendtrace.store")

SERIES_DATASET = {"month": "timeseries_monthly", "day": "timeseries_daily"}


@dataclass(frozen=True)
class DatasetInfo:
    data_status: str
    data_version: str
    contract_version: str


class DataStore(Protocol):
    """Read-only access to served data. Errors are ApiError (INVALID_*, DATA_NOT_AVAILABLE).

    Rules for every implementation, including Member 1's real loader (audit M6; checked by
    ``backend/tests/test_store_conformance.py``, which runs against any store):

    * Load once. Read files at startup or on first use, then serve from memory. ``regions()``,
      ``variables()`` and ``sources()`` are called on almost every request, so a repeated call must not
      open files again.
    * Thread-safe and read-only. Up to 40 requests call the store at the same time (FastAPI's thread
      pool). Never change a returned object or shared state after loading; return the same objects.
    * Raise only ``ApiError``. An unknown region, variable, season or period, or a missing file or
      result, raises ``api_error("DATA_NOT_AVAILABLE", ..., {"dataset": <logical name>, ...ids})``.
      A ``KeyError``/``FileNotFoundError`` would reach the user as an unexplained INTERNAL_ERROR.
    * Never fall back to mock data, convert units, fill gaps or smooth values.
    """

    info: DatasetInfo

    def asset_statuses(self) -> dict[str, str | None]: ...
    def variables(self) -> list[VariableInfo]: ...
    def regions(self) -> RegionsResult: ...
    def sources(self) -> list[SourceInfo]: ...
    def series(self, region_id: str, variable: str, frequency: str) -> TimeSeries: ...
    def trend(self, region_id: str, variable: str, period: Period, season: str) -> TrendResult: ...
    def anomalies(self, region_id: str, variable: str, period: Period,
                  detrended: bool) -> AnomalyResult | AnomalyBothResult: ...
    def interaction(self, region_id: str, season: str) -> InteractionResult: ...
    def indicator(self, region_id: str, indicator: str, season: str) -> IndicatorResult: ...


# ----------------------------------------------------------------- file layout (shared with the generator)

def variables_path() -> str: return "variables.json"
def regions_path() -> str: return "regions.json"
def sources_path() -> str: return "sources.json"
def series_path(region_id: str, variable: str, frequency: str) -> str:
    return f"timeseries/{region_id}_{variable}_{frequency}.json"
def trend_path(region_id: str, variable: str, season: str, period: Period) -> str:
    return f"trend/{region_id}_{variable}_{season}_{period.start}_{period.end}.json"
def anomalies_path(region_id: str, variable: str, detrended: bool) -> str:
    return f"anomalies/{region_id}_{variable}_{'detrended' if detrended else 'raw'}.json"
def interaction_path(region_id: str, season: str) -> str:
    return f"interaction/{region_id}_{season}.json"
def indicator_path(region_id: str, indicator: str, season: str) -> str:
    return f"indicators/{region_id}_{indicator}_{season}.json"


def model_for_path(relative: str) -> Any:
    """Pydantic type stored in a fixture file, from its path (used by store and tests)."""
    top = relative.split("/", 1)[0]
    return {
        "variables.json": list[VariableInfo], "regions.json": RegionsResult, "sources.json": list[SourceInfo],
        "timeseries": TimeSeries, "trend": TrendResult, "interaction": InteractionResult,
        "indicators": IndicatorResult,
        "anomalies": AnomalyBothResult if "_both_" in relative else AnomalyResult,
    }[top]


# ----------------------------------------------------------------- mock implementation


class MockStore:
    """Serves generated fixtures from data/mock/<scenario>/. Never used when DATA_MODE=real."""

    def __init__(self, scenario_dir: Path) -> None:
        self._dir = scenario_dir
        if not (scenario_dir / variables_path()).is_file():
            raise ConfigError(
                f"Mock data not found in {scenario_dir.name!r}. Run: python scripts/generate_mock_data.py"
            )
        self._loaded: dict[str, str | None] = {}
        self._load = lru_cache(maxsize=256)(self._load_uncached)
        first = self._load(variables_path())
        if first.data_status != "mock":
            raise ConfigError("Mock directory contains a file not labelled data_status=mock")
        self.info = DatasetInfo(first.data_status, first.data_version, first.contract_version)

    def _load_uncached(self, relative: str) -> Envelope[Any]:
        path = self._dir / relative
        if not path.is_file():
            raise FileNotFoundError(relative)
        raw = json.loads(path.read_text(encoding="utf-8"))
        envelope = TypeAdapter(Envelope[model_for_path(relative)]).validate_python(raw)
        self._loaded[relative] = envelope.data_status
        return envelope

    def _envelope(self, relative: str) -> Envelope[Any]:
        envelope = self._load(relative)
        if envelope.data_status != "mock" or envelope.data_version != self.info.data_version:
            raise RuntimeError(f"Inconsistent provenance in mock asset {relative}")
        return envelope

    def _result(self, relative: str, dataset: str, **ids: Any) -> Any:
        try:
            return self._envelope(relative).result
        except FileNotFoundError:
            raise api_error("DATA_NOT_AVAILABLE", "This data is not available yet.",
                            {"dataset": dataset, **ids}) from None

    def asset_statuses(self) -> dict[str, str | None]:
        return dict(self._loaded)

    def variables(self) -> list[VariableInfo]:
        return self._result(variables_path(), "variables")

    def regions(self) -> RegionsResult:
        return self._result(regions_path(), "regions")

    def sources(self) -> list[SourceInfo]:
        return self._result(sources_path(), "sources")

    def series(self, region_id: str, variable: str, frequency: str) -> TimeSeries:
        return self._result(series_path(region_id, variable, frequency), SERIES_DATASET[frequency],
                            region_id=region_id, variable=variable)

    def trend(self, region_id: str, variable: str, period: Period, season: str) -> TrendResult:
        return self._result(trend_path(region_id, variable, season, period), "trend",
                            region_id=region_id, variable=variable, season=season, **period.model_dump())

    def anomalies(self, region_id: str, variable: str, period: Period,
                  detrended: bool) -> AnomalyResult | AnomalyBothResult:
        full = self._result(anomalies_path(region_id, variable, detrended), "anomalies",
                            region_id=region_id, variable=variable, detrended=detrended)
        return window_anomalies(full, period)

    def interaction(self, region_id: str, season: str) -> InteractionResult:
        return self._result(interaction_path(region_id, season), "interaction_summary",
                            region_id=region_id, season=season)

    def indicator(self, region_id: str, indicator: str, season: str) -> IndicatorResult:
        return self._result(indicator_path(region_id, indicator, season), "rainfall_indicators",
                            region_id=region_id, indicator=indicator, season=season)


def _in_window(day: Any, period: Period) -> bool:
    return period.start <= day.strftime("%Y-%m") <= period.end


def _window_single(result: AnomalyResult, period: Period, suffix: str) -> AnomalyResult:
    return result.model_copy(update={
        "anomalies": [a for a in result.anomalies if _in_window(a.date, period)],
        "period": period,
        "result_id": f"anomalies_{result.region_id}_{result.variable}_{period.start}_{period.end}_{suffix}",
    })


def window_anomalies(full: AnomalyResult | AnomalyBothResult, period: Period) -> AnomalyResult | AnomalyBothResult:
    """List only the requested window (decision G-2): slicing, not recomputation."""
    if isinstance(full, AnomalyResult):
        return _window_single(full, period, "detrended" if full.baseline.detrended else "raw")
    suffix = "detrended" if full.detrended else "raw"
    return full.model_copy(update={
        "results": [_window_single(r, period, suffix) for r in full.results],
        "combined_flags": [f for f in full.combined_flags if _in_window(f.date, period)],
        "period": period,
        "result_id": f"anomalies_{full.region_id}_both_{period.start}_{period.end}_{suffix}",
    })


# ----------------------------------------------------------------- factory + startup checks


def build_store(settings: Settings) -> DataStore:
    if settings.data_mode == "mock":
        return MockStore(settings.mock_dir / settings.mock_scenario)
    try:
        real_module = importlib.import_module("app.services.real_store")
    except ModuleNotFoundError as exc:
        if exc.name != "app.services.real_store":
            raise  # the loader exists but one of its own imports is missing: a real error
        if settings.is_prod:
            raise ConfigError(
                "DATA_MODE=real needs Adrian's loader (app/services/real_store.py with create_store(settings)); "
                "it is not available yet. Mock data is never used as a fallback."
            ) from exc
        from .unavailable_store import UnavailableRealStore  # STUB: dev only, serves no data at all

        logger.warning("DATA_MODE=real without app/services/real_store.py: every data route returns "
                       "DATA_NOT_AVAILABLE (dev stub; never mock data)")
        return UnavailableRealStore(settings.contract_version)
    return real_module.create_store(settings)


def verify_store(store: DataStore, settings: Settings) -> None:
    """Startup checks on what was actually loaded (not on folder names or config)."""
    if settings.data_version_pin and store.info.data_version != settings.data_version_pin:
        raise ConfigError(f"Loaded data_version {store.info.data_version!r} != DATA_VERSION pin")
    if store.info.data_status != settings.data_mode:
        raise ConfigError("Loaded data_status does not match DATA_MODE; refusing to relabel data")
    if store.info.contract_version != settings.contract_version:
        raise ConfigError("Loaded data was produced for a different contract_version")
    if not settings.is_prod:
        return
    statuses = store.asset_statuses()
    if not statuses:
        raise ConfigError("Production start refused: the store attested no loaded assets")
    bad = sorted(name for name, status in statuses.items() if status != "real")
    if bad:
        raise ConfigError(f"Production start refused: assets without real provenance: {bad[:5]}")


def get_store(request: Request) -> DataStore:
    return request.app.state.store
