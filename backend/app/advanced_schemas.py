"""Contract sections G, H, I and J (rainfall indicators): G1 Member 2's models.

Kept apart from schemas.py (Member 1's A-F) so the two files merge cleanly.
Every rule below mirrors docs/contract.md; all of it is [PROVISIONAL] until the
H3 freeze. Decision IDs (G-1, H-2, ...) point to docs/decisions.md.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, model_validator

from .schemas import (
    ContractModel, Fraction, Interval, Percent, Period, PeriodStr, Probability, QcFlag, Season,
    TrendResult, check_interval,
)


class FrozenContractModel(ContractModel):
    """G–J objects are cached and shared by concurrent requests, so they cannot be changed after
    validation (audit LOW). Use ``model_copy(update=...)`` to derive a new object."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- G. anomalies

RAINFALL_CATEGORIES = ("unusually_wet", "unusually_dry")
AOD_CATEGORIES = ("unusually_high_aod", "unusually_low_aod")
AnomalyCategory = Literal["unusually_wet", "unusually_dry", "unusually_high_aod", "unusually_low_aod"]
CombinedCategory = Literal["dry_and_high_aod", "wet_and_high_aod", "unusual_combination"]
SCORE_TYPE_FOR_STATISTIC = {"empirical_percentile": "percentile", "z_log": "z_log"}


class AnomalyBaseline(FrozenContractModel):
    start: PeriodStr
    end: PeriodStr
    method: Literal["same_calendar_month"]
    statistic: Literal["empirical_percentile", "z_log"]
    detrended: bool


class AnomalyThresholds(FrozenContractModel):
    high: float
    low: float
    min_valid_fraction: Fraction | None  # rainfall 0.9 (G3 section 9); AOD null (decision G-4)
    dry_suppression_median: float | None  # mm/month, rainfall only (G-5)

    @model_validator(mode="after")
    def _ordered(self) -> "AnomalyThresholds":
        if self.low >= self.high:
            raise ValueError("thresholds.low must be below thresholds.high")
        return self


class AnomalyEntry(FrozenContractModel):
    date: date
    value: float | None
    baseline_median: float | None
    score: float | None
    score_type: Literal["percentile", "z_log"]
    category: AnomalyCategory | None
    valid_fraction: Fraction | None
    qc_flag: QcFlag
    note: str

    @model_validator(mode="after")
    def _consistent(self) -> "AnomalyEntry":
        if self.date.day != 1:
            raise ValueError("anomaly dates are monthly: YYYY-MM-01")
        if (self.value is None) != (self.qc_flag == "missing"):
            raise ValueError("value is null exactly when qc_flag is 'missing'")
        if self.value is None and (self.score is not None or self.category is not None):
            raise ValueError("a missing month has no score and no category")
        if self.category is not None and self.score is None:
            raise ValueError("a flagged month needs a score")
        return self


class AnomalyResult(FrozenContractModel):
    result_id: str
    region_id: str
    variable: Literal["rainfall", "aod"]
    source_id: str
    unit: str
    period: Period
    baseline: AnomalyBaseline
    thresholds: AnomalyThresholds
    anomalies: list[AnomalyEntry]

    @model_validator(mode="after")
    def _rules(self) -> "AnomalyResult":
        allowed = RAINFALL_CATEGORIES if self.variable == "rainfall" else AOD_CATEGORIES
        score_type = SCORE_TYPE_FOR_STATISTIC[self.baseline.statistic]
        dates = [a.date for a in self.anomalies]
        if dates != sorted(dates) or len(set(dates)) != len(dates):
            raise ValueError("anomalies must be in ascending date order without duplicates")
        for entry in self.anomalies:
            _check_entry(entry, allowed, score_type, self.thresholds, self.period)
        return self


def _check_entry(entry: AnomalyEntry, allowed: tuple[str, ...], score_type: str,
                 thresholds: AnomalyThresholds, period: Period) -> None:
    if entry.score_type != score_type:
        raise ValueError("score_type must match baseline.statistic")
    if not period.start <= entry.date.strftime("%Y-%m") <= period.end:
        raise ValueError("anomaly date outside the requested period")
    if entry.category is None:
        return
    if entry.category not in allowed:
        raise ValueError(f"category {entry.category} is not allowed for this variable")
    is_high = entry.category in ("unusually_wet", "unusually_high_aod")
    if is_high and entry.score < thresholds.high:
        raise ValueError("high/wet category needs score >= thresholds.high (inclusive, decision G-6)")
    if not is_high and entry.score > thresholds.low:
        raise ValueError("low/dry category needs score <= thresholds.low (inclusive, decision G-6)")


class CombinedFlag(FrozenContractModel):
    date: date
    category: CombinedCategory
    rainfall_category: Literal["unusually_wet", "unusually_dry"]
    aod_category: Literal["unusually_high_aod", "unusually_low_aod"]


COMBINED_RULE = {
    ("unusually_dry", "unusually_high_aod"): "dry_and_high_aod",
    ("unusually_wet", "unusually_high_aod"): "wet_and_high_aod",
}


def combined_category(rainfall_category: str, aod_category: str) -> str:
    """[PROVISIONAL] decision G-7: any other both-flagged pair is 'unusual_combination'."""
    return COMBINED_RULE.get((rainfall_category, aod_category), "unusual_combination")


class AnomalyBothResult(FrozenContractModel):
    result_id: str
    region_id: str
    variable: Literal["both"]
    period: Period
    detrended: bool
    results: list[AnomalyResult] = Field(min_length=2, max_length=2)
    combined_flags: list[CombinedFlag]

    @model_validator(mode="after")
    def _rules(self) -> "AnomalyBothResult":
        rain, aod = self.results
        if (rain.variable, aod.variable) != ("rainfall", "aod"):
            raise ValueError("results must be [rainfall, aod] in that order")
        for item in self.results:
            if item.region_id != self.region_id or item.period != self.period:
                raise ValueError("nested results must share region_id and period")
            if item.baseline.detrended != self.detrended:
                raise ValueError("nested baselines must share detrended")
        rain_cats = {a.date: a.category for a in rain.anomalies if a.category}
        aod_cats = {a.date: a.category for a in aod.anomalies if a.category}
        expected = [
            (d, combined_category(rain_cats[d], aod_cats[d]), rain_cats[d], aod_cats[d])
            for d in sorted(set(rain_cats) & set(aod_cats))
        ]
        actual = [(f.date, f.category, f.rainfall_category, f.aod_category) for f in self.combined_flags]
        if actual != expected:
            raise ValueError("combined_flags must list exactly the months flagged in both variables")
        return self


# --------------------------------------------------------------------------- H. interaction

INTERACTION_GUARDRAIL = "Association only. AOD is retrieved in clear skies, so rainy days are under-sampled."
TOO_FEW_EVENTS_NOTE = "too few events for a reliable comparison"
MIN_EVENTS_FOR_TEST = 10
Correlation = Annotated[float, Field(ge=-1.0, le=1.0)]


class InteractionSources(FrozenContractModel):
    rainfall_daily: str
    aod_daily: str
    rainfall_monthly: str
    aod_monthly: str


class EventDefinition(FrozenContractModel):
    rain_threshold: Literal["seasonal_p90_of_daily_regional_mean"]
    threshold_period: Period
    min_separation_days: int = Field(ge=1)
    window_days: int = Field(ge=1)
    event_day_excluded: bool
    min_valid_aod_days_per_window: int = Field(ge=1)


class InteractionControl(FrozenContractModel):
    method: Literal["random_non_event_days_same_month"]
    n: int = Field(ge=0)
    median_change: float | None


class MonthlyAssociation(FrozenContractModel):
    method: Literal["spearman_on_deseasonalised_anomalies"]
    rho: Correlation | None
    n: int = Field(ge=0)
    p_value: Probability | None


class InteractionResult(FrozenContractModel):
    result_id: str
    region_id: str
    season: Season
    period: Period
    source_ids: InteractionSources
    event_definition: EventDefinition
    status: Literal["ok", "too_few_events"]
    note: str | None
    n_events: int = Field(ge=0)
    n_events_used: int = Field(ge=0)
    valid_aod_pct_before: Percent | None
    valid_aod_pct_after: Percent | None
    aod_before_median: float | None
    aod_after_median: float | None
    median_change: float | None
    median_change_ci: Interval | None
    ci_level: float
    ci_method: Literal["bootstrap"]
    test: Literal["wilcoxon_signed_rank"]
    p_value: Probability | None
    control: InteractionControl
    monthly_association: MonthlyAssociation
    guardrail: Literal["Association only. AOD is retrieved in clear skies, so rainy days are under-sampled."]

    @model_validator(mode="after")
    def _rules(self) -> "InteractionResult":
        check_interval("median_change_ci", self.median_change_ci)
        if self.n_events_used > self.n_events:
            raise ValueError("n_events_used cannot exceed n_events")
        enough = self.n_events_used >= MIN_EVENTS_FOR_TEST
        if self.status != ("ok" if enough else "too_few_events"):
            raise ValueError("status must be 'ok' iff n_events_used >= 10")
        if enough and (self.note is not None or self.p_value is None or self.median_change_ci is None):
            raise ValueError("an 'ok' result has a test result and no note")
        if not enough and (self.note != TOO_FEW_EVENTS_NOTE or self.p_value is not None
                           or self.median_change_ci is not None):
            raise ValueError("a too_few_events result has the note and no inferential result")
        if self.n_events == 0 and (self.valid_aod_pct_before is not None or self.valid_aod_pct_after is not None):
            raise ValueError("valid AOD percentages are null when there are no events")
        if self.n_events_used == 0 and any(
            v is not None for v in (self.aod_before_median, self.aod_after_median, self.median_change)
        ):
            raise ValueError("medians are null when no event was usable")
        return self


# --------------------------------------------------------------------------- J. rainfall indicators

IndicatorName = Literal["heavy_rain_share", "longest_dry_spell", "rx5day"]
IndicatorSeason = Literal["annual", "JJAS", "OND"]


class IndicatorValue(FrozenContractModel):
    year: int
    value: float | None
    valid_fraction: Fraction | None


class IndicatorResult(FrozenContractModel):
    result_id: str
    region_id: str
    indicator: IndicatorName
    season: IndicatorSeason
    period: Period
    source_id: str
    unit: str
    definition: str
    spatial_method: Literal["regional_mean", "point_median", "grid_mean"]
    threshold_baseline: Period | None
    min_valid_fraction: Fraction
    values: list[IndicatorValue]
    trend: TrendResult | None
    trend_note: str | None

    @model_validator(mode="after")
    def _rules(self) -> "IndicatorResult":
        years = [v.year for v in self.values]
        first, last = int(self.period.start[:4]), int(self.period.end[:4])
        if years != list(range(first, last + 1)):
            raise ValueError("values must list every year of the period once, in order")
        for item in self.values:
            if item.valid_fraction is None or item.valid_fraction < self.min_valid_fraction:
                if item.value is not None:
                    raise ValueError("years below min_valid_fraction must have value null (G3 rule)")
        if (self.trend is None) == (self.trend_note is None):
            raise ValueError("give either a trend or a trend_note explaining its absence")
        if self.trend is not None and self.trend.region_id != self.region_id:
            raise ValueError("trend region must match")
        return self


# --------------------------------------------------------------------------- reports (DOCX §5.1)

ReportSection = Literal["trend", "anomalies", "interaction", "indicators"]


class ReportRequest(FrozenContractModel):
    """POST /report body. One region for the MVP (decision R-2)."""

    # No max_length on these strings: a wrong value of any length must get the same INVALID_* code
    # (audit M2). The values are checked against fixed lists, never echoed, and MAX_BODY_BYTES caps the body.
    region_id: str
    variables: list[str] = Field(min_length=1, max_length=2)
    start: str
    end: str
    season: str = "all"
    include: list[ReportSection] = Field(default_factory=lambda: ["trend"], min_length=1, max_length=4)
    include_ai_summary: bool = False

    @model_validator(mode="after")
    def _unique(self) -> "ReportRequest":
        if len(set(self.variables)) != len(self.variables) or len(set(self.include)) != len(self.include):
            raise ValueError("variables and include must not repeat")
        return self


class ReportCreated(FrozenContractModel):
    report_id: str
    url: str
    pages: int = Field(ge=1)
    generated_at: str


# --------------------------------------------------------------------------- I. errors


class ErrorBody(FrozenContractModel):
    code: str
    message: str
    details: dict[str, Any]


class ErrorResponse(FrozenContractModel):
    error: ErrorBody
