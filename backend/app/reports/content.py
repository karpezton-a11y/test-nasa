"""Typed inputs for the PDF builder (no ReportLab/matplotlib imports here).

Integration hooks for later:
- ``methods_text``: Group 3's reviewed methods.md text (H9).
- ``ai_summary``: Member 1's /explain output ({text, source: llm|template}).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union

from pydantic import BaseModel

from ..advanced_schemas import AnomalyBothResult, AnomalyResult, IndicatorResult, InteractionResult
from ..schemas import Period, Region, SourceInfo, TimeSeries, TrendResult


@dataclass(frozen=True)
class Unavailable:
    """A requested section whose data does not exist yet (decision R-3)."""

    reason: str


@dataclass(frozen=True)
class AiSummary:
    text: str
    source: Literal["llm", "template"]


@dataclass(frozen=True)
class VariableSection:
    variable: str
    label: str
    unit: str
    unit_label: str
    series: Union[TimeSeries, Unavailable]
    trend: Union[TrendResult, Unavailable, None]  # None = trend not requested


@dataclass(frozen=True)
class ReportContent:
    app_name: str
    data_status: str
    data_version: str
    contract_version: str
    generated_at: str
    region: Region
    period: Period
    season: str
    include: tuple[str, ...]
    variables: tuple[VariableSection, ...]
    anomalies: Union[AnomalyResult, AnomalyBothResult, Unavailable, None] = None
    interaction: Union[InteractionResult, Unavailable, None] = None
    indicators: tuple[tuple[str, Union[IndicatorResult, Unavailable]], ...] | None = None
    sources: tuple[SourceInfo, ...] = field(default_factory=tuple)
    methods_text: str | None = None
    limitations_text: tuple[str, ...] | None = None  # Group 3 methods.md "## Limitations" bullets (H9)
    include_ai_summary: bool = False
    ai_summary: AiSummary | None = None

    @property
    def is_mock(self) -> bool:
        return self.data_status == "mock"

    def result_objects(self) -> list[BaseModel]:
        """The computed result objects printed in this report (input for the AI summary hook)."""
        items: list[object] = [s.trend for s in self.variables]
        items += [self.anomalies, self.interaction, *(r for _, r in (self.indicators or ()))]
        return [item for item in items if isinstance(item, BaseModel)]
