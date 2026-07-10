"""财务语义层数据模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CoverageStatus = Literal["ok", "partial", "clarify", "unavailable"]
CoverageStrategy = Literal[
    "annual_direct",
    "sum_quarters",
    "latest_annual",
    "latest_available",
    "partial_compare",
    "clarify_for_granularity",
    "unavailable",
]
MatchType = Literal["global_alias", "company_override"]
QueryType = Literal["lookup", "latest", "compare", "trend"]
AnswerPolicy = Literal[
    "direct",
    "compare_with_mixed_source_metrics",
    "partial_compare",
    "sum_quarters_disclosure",
    "trend_with_gaps",
    "clarify_for_granularity",
    "unavailable",
]


class CanonicalMetricDefinition(BaseModel):
    code: str
    name: str
    description: str = ""


class CompanyMetricOverride(BaseModel):
    company_key: str
    canonical_metric_code: str
    metric_name: str


class CompanyMetricMatch(BaseModel):
    company_key: str
    company_id: int | None = None
    metric_id: int | None = None
    metric_name: str
    match_type: MatchType
    confidence: float = Field(ge=0.0, le=1.0)


class CanonicalMetricMatch(BaseModel):
    canonical_metric_code: str
    canonical_metric_name: str
    requested_metric: str
    company_metric_matches: list[CompanyMetricMatch] = Field(default_factory=list)


class CoverageRequest(BaseModel):
    canonical_matches: list[CanonicalMetricMatch]
    companies: list[str]
    years: list[int] = Field(default_factory=list)
    query_type: QueryType = "lookup"
    template_id: str = ""


class CompanyCoverage(BaseModel):
    company_key: str
    company_id: int
    metric_id: int
    canonical_metric_code: str
    metric_name: str
    available_period_types: list[str] = Field(default_factory=list)
    available_years: list[int] = Field(default_factory=list)
    selected_strategy: CoverageStrategy = "unavailable"
    selected_year: int | None = None


class CoverageResolution(BaseModel):
    status: CoverageStatus = "unavailable"
    canonical_metric_code: str = ""
    company_coverages: list[CompanyCoverage] = Field(default_factory=list)
    answer_policy: AnswerPolicy = "unavailable"
    clarify_reason: str = ""
    unavailable_reason: str = ""


class ResolvedMetricBinding(BaseModel):
    company_id: int
    company_key: str = ""
    metric_id: int
    canonical_metric_code: str
    metric_name: str = ""
    selected_strategy: CoverageStrategy = "annual_direct"
    selected_year: int | None = None


__all__ = [
    "AnswerPolicy",
    "CanonicalMetricDefinition",
    "CanonicalMetricMatch",
    "CompanyCoverage",
    "CompanyMetricMatch",
    "CompanyMetricOverride",
    "CoverageRequest",
    "CoverageResolution",
    "CoverageStatus",
    "CoverageStrategy",
    "MatchType",
    "QueryType",
    "ResolvedMetricBinding",
]
