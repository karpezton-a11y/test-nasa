"""Shared request validation helpers (IDs, periods, coverage).

[PROVISIONAL] Member 1 owns /timeseries validation; until his helpers land,
these are the single implementation used by every G1 M2 route. Signatures are
listed in README "Agreements with Member 1". Only counting/filtering here;
no statistics.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from typing import get_args

from ..errors import api_error
from ..schemas import PERIOD_PATTERN, Frequency, Period, Season, SeriesPoint, TimeSeries

PERIOD_RE = re.compile(PERIOD_PATTERN)
SEASONS: tuple[str, ...] = get_args(Season)
FREQUENCIES: tuple[str, ...] = get_args(Frequency)
MIN_TREND_YEARS = 10
MIN_VALID_PCT = 70.0
MAX_DAILY_MONTHS = 120  # daily requests: at most 10 years per call


def require_choice(value: str, allowed: list[str] | tuple[str, ...], code: str, param: str) -> str:
    if value not in allowed:
        raise api_error(code, f"Unknown {param}. Choose one of: {', '.join(allowed)}.",
                        {"param": param, "allowed": list(allowed)})
    return value


def _parse(value: str, param: str) -> tuple[int, int]:
    match = PERIOD_RE.fullmatch(value or "")
    if not match:
        raise api_error("INVALID_PERIOD", f"{param} must look like YYYY-MM.", {"param": param, "reason": "bad_format"})
    return int(match.group(1)), int(match.group(2))


def resolve_period(start: str | None, end: str | None, available: Period) -> Period:
    """Defaults to the available period; checks format, order and availability."""
    start = available.start if start is None else start
    end = available.end if end is None else end
    _parse(start, "start")
    _parse(end, "end")
    details = {"available": available.model_dump()}
    if start > end:
        raise api_error("INVALID_PERIOD", "The start month is after the end month.",
                        {"param": "start", "reason": "start_after_end", **details})
    if start < available.start or end > available.end:
        raise api_error("INVALID_PERIOD", "The period is outside the available data.",
                        {"param": "start" if start < available.start else "end", "reason": "outside_available", **details})
    return Period(start=start, end=end)


def months_in(period: Period) -> int:
    (y1, m1), (y2, m2) = _parse(period.start, "start"), _parse(period.end, "end")
    return (y2 - y1) * 12 + (m2 - m1) + 1


def period_years(period: Period) -> float:
    return months_in(period) / 12


def first_day(period: Period) -> date:
    year, month = _parse(period.start, "start")
    return date(year, month, 1)


def last_day(period: Period) -> date:
    year, month = _parse(period.end, "end")
    return date(year, month, calendar.monthrange(year, month)[1])


def require_daily_limit(period: Period) -> None:
    if months_in(period) > MAX_DAILY_MONTHS:
        raise api_error("INVALID_PERIOD", "Daily data can be requested for at most 10 years at a time.",
                        {"param": "end", "reason": "daily_limit_exceeded", "max_years": 10})


def require_min_years(period: Period, min_years: int = MIN_TREND_YEARS) -> None:
    years = period_years(period)
    if years < min_years:
        raise api_error("PERIOD_TOO_SHORT", f"Choose at least {min_years} years.",
                        {"min_years": min_years, "requested_years": round(years, 2)})


def slice_series(series: TimeSeries, period: Period) -> TimeSeries:
    """New TimeSeries with the points inside the period (inclusive); input untouched."""
    lo, hi = first_day(period), last_day(period)
    return series.model_copy(update={"points": [p for p in series.points if lo <= p.date <= hi]})


@dataclass(frozen=True)
class Coverage:
    n_valid: int
    n_expected: int

    @property
    def valid_pct(self) -> float:
        return 100.0 * self.n_valid / self.n_expected if self.n_expected else 0.0


def _is_valid(point: SeriesPoint) -> bool:
    return point.value is not None and point.qc_flag != "suspect"


def coverage(series: TimeSeries, period: Period, season: str = "all") -> Coverage:
    """[PROVISIONAL] decision C-2: n_expected = slots in the period (months or days);
    a slot counts as valid when its value is present and not 'suspect'."""
    expected = months_in(period) if series.frequency == "month" else (last_day(period) - first_day(period)).days + 1
    months = {"all": set(range(1, 13)), "JF": {1, 2}, "MAM": {3, 4, 5},
              "JJAS": {6, 7, 8, 9}, "OND": {10, 11, 12}}[season]
    if season != "all":
        y1, m1 = _parse(period.start, "start")
        expected = 0
        for offset in range(months_in(period)):
            year, month0 = divmod(y1 * 12 + m1 - 1 + offset, 12)
            if month0 + 1 in months:
                expected += 1 if series.frequency == "month" else calendar.monthrange(year, month0 + 1)[1]
    n_valid = sum(1 for p in slice_series(series, period).points if p.date.month in months and _is_valid(p))
    return Coverage(n_valid=n_valid, n_expected=expected)


def require_coverage(series: TimeSeries, period: Period, min_pct: float = MIN_VALID_PCT, *, season: str = "all") -> Coverage:
    cov = coverage(series, period, season)
    if cov.valid_pct < min_pct:
        raise api_error(
            "INSUFFICIENT_DATA",
            f"Too many missing values in this period: fewer than {min_pct:g}% of expected values are valid.",
            {"min_valid_pct": min_pct, "valid_pct": round(cov.valid_pct, 1),
             "n_valid": cov.n_valid, "n_expected": cov.n_expected},
        )
    return cov
