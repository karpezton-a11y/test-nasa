"""Requests and core response compositions; reuse existing A–J result models."""
from typing import Any, Literal

from pydantic import Field, StrictBool, model_validator

from .advanced_schemas import AnomalyBothResult, AnomalyResult, IndicatorResult, InteractionResult, MonthlyAssociation
from .schemas import ContractModel, TrendResult


class AnalyzeOptions(ContractModel):
    alpha: Literal[0.01, 0.05, 0.10] = 0.05
    exclude_low_coverage: StrictBool = False


class AnalyzeRequest(ContractModel):
    region_id: str = Field(max_length=32)
    variable: str = Field(max_length=32)
    start: str | None = Field(default=None, max_length=7)
    end: str | None = Field(default=None, max_length=7)
    season: str = Field(default="all", max_length=8)
    options: AnalyzeOptions = Field(default_factory=AnalyzeOptions)


class CompareRequest(ContractModel):
    mode: Literal["regions", "variables"]
    region_ids: list[str] | None = Field(default=None, min_length=2, max_length=4)
    region_id: str | None = Field(default=None, max_length=32)
    variable: str | None = Field(default=None, max_length=32)
    variables: list[str] | None = Field(default=None, min_length=2, max_length=2)
    start: str | None = Field(default=None, max_length=7)
    end: str | None = Field(default=None, max_length=7)
    season: str = Field(default="all", max_length=8)

    @model_validator(mode="after")
    def _mode(self):
        if self.mode == "regions":
            if not self.region_ids or self.variable is None or self.region_id is not None or self.variables is not None:
                raise ValueError("regions mode requires region_ids and variable only")
            if len(set(self.region_ids)) != len(self.region_ids):
                raise ValueError("region_ids must be distinct")
        elif self.region_id is None or self.variables != ["rainfall", "aod"] or self.region_ids is not None or self.variable is not None:
            raise ValueError('variables mode requires region_id and variables=["rainfall","aod"] only')
        return self


class CompareSummary(ContractModel):
    same_direction: bool | None
    note: str


class CompareResult(ContractModel):
    mode: Literal["regions", "variables"]
    results: list[TrendResult]
    summary: CompareSummary
    monthly_association: MonthlyAssociation | None = None


ScientificResult = TrendResult | AnomalyBothResult | AnomalyResult | InteractionResult | IndicatorResult


class SummaryResult(ContractModel):
    # [PROVISIONAL] AI-01: the spec gives no standalone summary input shape.
    results: list[ScientificResult] = Field(min_length=1, max_length=8)


class ExplainRequest(ContractModel):
    result_type: Literal["trend", "anomaly", "interaction", "summary"]
    result_id: str | None = Field(default=None, min_length=1, max_length=256)
    result: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _one_source(self):
        if (self.result_id is None) == (self.result is None):
            raise ValueError("provide exactly one of result_id or result")
        return self


class GuardrailResult(ContractModel):
    passed: bool
    issues: list[str]


class Explanation(ContractModel):
    text: str
    key_points: list[str]
    caveats: list[str]
    source: Literal["llm", "template"]
    guardrail: GuardrailResult


class LlmOutput(ContractModel):
    text: str = Field(min_length=1, max_length=4000)
    key_points: list[str] = Field(max_length=3)
    caveats: list[str] = Field(max_length=2)
    numbers_used: list[str]
