"""Only bridge to the statistics package (analysis/trendlib). This module never calculates a statistic."""
from __future__ import annotations

import importlib
import inspect
import logging
import sys
from typing import Any, Callable

from ..config import REPO_ROOT
from ..errors import api_error
from ..schemas import Evidence, Period, TimeSeries, TrendResult

logger = logging.getLogger("trendtrace.science")
ANALYSIS_DIR = REPO_ROOT / "analysis"


def _import_trendlib():
    try:
        return importlib.import_module("trendlib")
    except ModuleNotFoundError as exc:
        if exc.name != "trendlib":
            raise
        # The package ships in this repository; use it without a separate install step so
        # Render/CI/laptops all run the same statistics (pip install -e analysis also works).
        if (ANALYSIS_DIR / "trendlib" / "__init__.py").is_file() and sys.modules.get("trendlib", 0) is not None:
            if str(ANALYSIS_DIR) not in sys.path:
                sys.path.append(str(ANALYSIS_DIR))
            return importlib.import_module("trendlib")
        raise


def trendlib_available() -> bool:
    try:
        _import_trendlib()
        return True
    except ModuleNotFoundError:
        return False


def trendlib_version() -> str | None:
    try:
        return getattr(_import_trendlib(), "__version__", None)
    except ModuleNotFoundError:
        return None


def _trendlib():
    try:
        return _import_trendlib()
    except ModuleNotFoundError as exc:
        if exc.name != "trendlib":
            raise  # broken internal dependency is a programming/deployment error
        logger.error("trendlib is not importable; install with pip install -e analysis")
        raise api_error("DATA_NOT_AVAILABLE", "The scientific analysis package is not available yet.",
                        {"dataset": "trendlib"}) from exc


def series_frame(series: TimeSeries, period: Period):
    """Contract frame passed to trendlib (decision SCI-01): explicit dates keep missing slots."""
    import pandas as pd

    frame = pd.DataFrame([p.model_dump() for p in series.points],
                         columns=["date", "value", "valid_fraction", "qc_flag"])
    frame.attrs.update(region_id=series.region_id, variable=series.variable,
                       source_id=series.source_id, unit=series.unit,
                       frequency=series.frequency, period=period.model_dump())
    return frame


def quality_errors() -> tuple[type[Exception], ...]:
    return _quality_errors(_trendlib())


def _quality_errors(module) -> tuple[type[Exception], ...]:
    # [PROVISIONAL] SCI-02: Aadarsh confirms these public classes. Never catch
    # ValueError/Exception wholesale, or identify exceptions by message text.
    namespaces = [module]
    if getattr(module, "exceptions", None) is not None:
        namespaces.append(module.exceptions)
    return tuple(cls for ns in namespaces for name in ("InsufficientDataError", "DataQualityError")
                 if isinstance(cls := getattr(ns, name, None), type) and issubclass(cls, Exception))


def compute_trend(series: TimeSeries, period: Period, season: str, *, alpha: float = 0.05,
                  exclude_low_coverage: bool = False,
                  mock_lookup: Callable[[], TrendResult] | None = None) -> TrendResult:
    """Pass a contract frame to trendlib; validate all scientific output unchanged.

    [PROVISIONAL] SCI-01: G3 accepts pandas columns date/value/valid_fraction/
    qc_flag and context in frame.attrs. Explicit dates preserve missing slots.
    Mock callers supply their existing fixture lookup; trendlib is never imported.
    """
    if mock_lookup is not None:
        result = mock_lookup().model_copy(deep=True)
        if result.method.alpha != alpha:
            raise api_error("DATA_NOT_AVAILABLE", "No fixture exists for this alpha.", {"dataset": "trend", "alpha": alpha})
    else:
        module = _trendlib()
        frame = series_frame(series, period)
        try:
            options = {}
            if exclude_low_coverage:
                if "exclude_low_coverage" not in inspect.signature(module.compute_trend).parameters:
                    raise api_error("DATA_NOT_AVAILABLE", "The science package does not support this sensitivity option yet.",
                                    {"dataset": "trend_options", "option": "exclude_low_coverage"})
                options["exclude_low_coverage"] = True
            raw: Any = module.compute_trend(frame, season=season, alpha=alpha, **options)
            raw = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
            evidence_fn = getattr(module, "compute_evidence", None)
            if callable(evidence_fn):
                evidence = evidence_fn(frame, raw, sensitivity=True)
                raw["evidence"] = Evidence.model_validate(evidence).model_dump()
            elif raw.get("evidence") is None:
                # No fabricated confidence label or undocumented not_assessed enum.
                raise api_error("DATA_NOT_AVAILABLE", "Scientific evidence is not available yet.",
                                {"dataset": "evidence"})
        except _quality_errors(module) as exc:
            logger.info("trendlib rejected data quality (%s)", type(exc).__name__)
            raise api_error("INSUFFICIENT_DATA", "There are not enough reliable observations for this analysis.",
                            {"dataset": "trend"}) from exc
        result = TrendResult.model_validate(raw)
    wanted = (series.region_id, series.variable, series.source_id, period, season, alpha)
    actual = (result.region_id, result.variable, result.source_id, result.period, result.season, result.method.alpha)
    if actual != wanted:
        raise RuntimeError("trendlib/fixture result does not match the requested analysis")
    return result
