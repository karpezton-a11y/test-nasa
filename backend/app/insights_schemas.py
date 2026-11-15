"""Request/response models for discovery and insight routes (additive; frozen A-J shapes unchanged)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .schemas import ContractModel, TrendResult


class SeriesRequest(ContractModel):
    """Exactly one input: a bundled research series, an inline series, or a Giovanni CSV."""
    research_id: str | None = Field(default=None, max_length=64)
    dates: list[str] | None = Field(default=None, max_length=1200)
    values: list[float | None] | None = Field(default=None, max_length=1200)
    giovanni_csv: str | None = Field(default=None, max_length=60000)
    conversion: Literal["none", "mmhr_to_mm_month", "mmday_to_mm_month", "kgm2s_to_mm_month", "k_to_c"] = "none"
    frequency: Literal["month", "year"] = "month"
    alpha: Literal[0.01, 0.05, 0.10] = 0.05
    deseasonalise: bool = True
    unit: str | None = Field(default=None, max_length=40)
    label: str | None = Field(default=None, max_length=80)
    place: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def _one_source(self) -> "SeriesRequest":
        given = [self.research_id is not None, self.dates is not None or self.values is not None,
                 self.giovanni_csv is not None]
        if sum(given) != 1:
            raise ValueError("provide exactly one of research_id, dates+values, or giovanni_csv")
        if given[1] and (self.dates is None or self.values is None or len(self.dates) != len(self.values)):
            raise ValueError("dates and values must both be given with the same length")
        if given[1] and len(self.dates) == 0:
            raise ValueError("dates and values must not be empty")
        return self


class DiscoverRequest(ContractModel):
    theme: str | None = Field(default=None, max_length=20)
    place_type: str | None = Field(default=None, max_length=20)
    question: str | None = Field(default=None, max_length=300)
    region_id: str | None = Field(default=None, max_length=32)
    limit: int = Field(default=6, ge=1, le=12)


class DetailResult(ContractModel):
    trend: TrendResult
    analysis: dict[str, Any]
    plain_language: str
