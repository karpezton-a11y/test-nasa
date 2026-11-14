"""Shared Pydantic v2 models (shared seam with Member 1).

Contents:
- Success envelope + health result (shared, Step 1).
- Sections B, C, D, E, F transcribed from the Group 1 DOCX section 6 so that
  fixtures, CSV and PDF code share the frozen shapes. Adrian owns A–F.
  Existing indicator extensions remain provisional pending the team decision.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

IST = timezone(timedelta(hours=5, minutes=30), name="IST")

DataStatus = Literal["real", "mock"]
Season = Literal["all", "JF", "MAM", "JJAS", "OND"]
Frequency = Literal["month", "day"]
QcFlag = Literal["ok", "low_coverage", "missing", "suspect"]
PERIOD_PATTERN = r"^(\d{4})-(0[1-9]|1[0-2])$"  # One shared YYYY-MM pattern.
PeriodStr = Annotated[str, StringConstraints(pattern=PERIOD_PATTERN)]
Fraction = Annotated[float, Field(ge=0.0, le=1.0)]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
Percent = Annotated[float, Field(ge=0.0, le=100.0)]
Interval = tuple[float, float]
T = TypeVar("T")


class ContractModel(BaseModel):
    """Base for contract objects: unknown fields are rejected, never silently kept."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def check_interval(name: str, interval: Interval | None) -> None:
    if interval is not None and interval[0] > interval[1]:
        raise ValueError(f"{name} lower bound is above its upper bound")


# --------------------------------------------------------------------------- envelope


class Envelope(ContractModel, Generic[T]):
    data_status: DataStatus
    data_version: str
    contract_version: str
    generated_at: AwareDatetime
    result: T


def now_ist() -> datetime:
    return datetime.now(IST).replace(microsecond=0)


def make_envelope(result: T, *, data_status: str, data_version: str, contract_version: str,
                  generated_at: datetime | None = None) -> Envelope[T]:
    return Envelope(
        data_status=data_status,
        data_version=data_version,
        contract_version=contract_version,
        generated_at=generated_at or now_ist(),
        result=result,
    )


class HealthResult(ContractModel):
    status: Literal["ok"]
    data_status: DataStatus
    data_version: str
    trendlib_version: str | None
    ai_available: bool


# --------------------------------------------------------------------------- A/C helpers


class Period(ContractModel):
    start: PeriodStr
    end: PeriodStr

    @model_validator(mode="after")
    def _ordered(self) -> "Period":
        if self.start > self.end:
            raise ValueError("period start is after end")
        return self


# --------------------------------------------------------------------------- B. variables and sources


class VariableInfo(ContractModel):
    variable: str
    label: str
    unit: str
    unit_label: str
    sources: list[str] = Field(min_length=1)
    description: str
    caveat: str | None


class SourceInfo(ContractModel):
    source_id: str
    product: str
    short_name: str
    version: str
    doi: str | None
    access_method: str
    access_date: date | None
    variable_name: str
    citation: str | None


# --------------------------------------------------------------------------- C. regions + GeoJSON


class Region(ContractModel):
    region_id: str
    name: str
    bbox: tuple[float, float, float, float]
    status: str
    description: str
    variables: list[str] = Field(min_length=1)
    period_available: Period

    @model_validator(mode="after")
    def _valid_bbox(self) -> "Region":
        min_lon, min_lat, max_lon, max_lat = self.bbox
        if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
            raise ValueError("bbox must be [min_lon, min_lat, max_lon, max_lat] within lon/lat ranges")
        return self


class PolygonGeometry(ContractModel):
    type: Literal["Polygon"]
    coordinates: list[list[tuple[float, float]]]

    @model_validator(mode="after")
    def _closed_rings(self) -> "PolygonGeometry":
        for ring in self.coordinates:
            if len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("polygon rings must be closed and have at least 4 positions")
        return self


class RegionFeatureProperties(ContractModel):
    region_id: str
    name: str
    status: str


class RegionFeature(ContractModel):
    type: Literal["Feature"]
    id: str
    geometry: PolygonGeometry
    properties: RegionFeatureProperties


class FeatureCollection(ContractModel):
    type: Literal["FeatureCollection"]
    features: list[RegionFeature]


class RegionsResult(ContractModel):
    regions: list[Region]
    geojson: FeatureCollection


# --------------------------------------------------------------------------- D. time series


class SeriesPoint(ContractModel):
    date: date
    value: float | None
    valid_fraction: Fraction | None
    qc_flag: QcFlag

    @model_validator(mode="after")
    def _missing_rule(self) -> "SeriesPoint":
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError("value must be finite or null")
        if (self.value is None) != (self.qc_flag == "missing"):
            raise ValueError("value is null exactly when qc_flag is 'missing'")
        return self


class TimeSeries(ContractModel):
    region_id: str
    variable: str
    frequency: Frequency
    unit: str
    source_id: str
    points: list[SeriesPoint]

    @model_validator(mode="after")
    def _dates(self) -> "TimeSeries":
        if self.frequency == "month" and any(p.date.day != 1 for p in self.points):
            raise ValueError("monthly dates must be YYYY-MM-01")
        dates = [p.date for p in self.points]
        if dates != sorted(dates) or len(set(dates)) != len(dates):
            raise ValueError("points must be in ascending date order without duplicates")
        return self


# --------------------------------------------------------------------------- E/F. trend + evidence


class TrendMethod(ContractModel):
    test: str
    slope: str
    alpha: Probability
    ci_level: Probability


class SensitivityRun(ContractModel):
    name: str
    sen_slope: float | None
    p_value: Probability | None
    same_sign: bool | None


class Evidence(ContractModel):
    record_years: float
    n_valid: int = Field(ge=0)
    n_expected: int = Field(ge=0)
    valid_obs_pct: Percent
    mean_valid_fraction: Fraction | None
    low_coverage_months: int = Field(ge=0)
    p_value: Probability
    slope_ci: Interval
    ci_excludes_zero: bool
    sensitivity: list[SensitivityRun]
    evidence_label: Literal["strong", "moderate", "weak", "insufficient_data"]
    label_rule_version: str
    notes: list[str]

    @model_validator(mode="after")
    def _counts_and_interval(self) -> "Evidence":
        if self.n_valid > self.n_expected or self.low_coverage_months > self.n_expected:
            raise ValueError("evidence counts exceed n_expected")
        check_interval("evidence.slope_ci", self.slope_ci)
        return self


class TrendResult(ContractModel):
    result_id: str
    region_id: str
    variable: str
    source_id: str
    period: Period
    # "annual" is a proposed extension for indicator trends (decision J-2).
    season: Season | Literal["annual"]
    series_type: str
    method: TrendMethod
    direction: Literal["increasing", "decreasing", "no_significant_trend"]
    slope_sign: Literal["positive", "negative", "zero"]
    sen_slope: float
    slope_unit: str
    slope_ci: Interval
    p_value: Probability
    significant: bool
    ols_slope: float
    ols_ci: Interval
    change_over_period: float
    baseline_mean: float
    percent_change_per_decade: float
    n_expected: int = Field(ge=0)
    n_valid: int = Field(ge=0)
    missing_pct: Percent
    record_years: float
    lag1_autocorrelation: float
    limitations: list[str]
    evidence: Evidence
    trendlib_version: str
    computed_at: AwareDatetime

    @model_validator(mode="after")
    def _direction_rule(self) -> "TrendResult":
        """[RULE] a non-significant slope is never called increasing/decreasing."""
        check_interval("slope_ci", self.slope_ci)
        check_interval("ols_ci", self.ols_ci)
        if self.significant != (self.p_value < self.method.alpha):
            raise ValueError("significant must equal p_value < alpha")
        sign = "positive" if self.sen_slope > 0 else "negative" if self.sen_slope < 0 else "zero"
        if self.slope_sign != sign:
            raise ValueError("slope_sign does not match sen_slope")
        expected = {"positive": "increasing", "negative": "decreasing"}.get(sign, "no_significant_trend")
        if (expected if self.significant else "no_significant_trend") != self.direction:
            raise ValueError("direction violates the direction rule (section E)")
        if self.n_valid > self.n_expected:
            raise ValueError("n_valid cannot exceed n_expected")
        for name in ("record_years", "n_valid", "n_expected", "p_value", "slope_ci"):
            if getattr(self.evidence, name) != getattr(self, name):
                raise ValueError(f"evidence.{name} must match the trend result")
        return self
