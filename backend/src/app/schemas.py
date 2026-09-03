from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class WireModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AnalystCreate(WireModel):
    name: str = Field(min_length=1, max_length=200)


class AnalystSummary(WireModel):
    id: str
    name: str
    followed: bool
    claim_count: int = 0
    resolved_count: int = 0
    open_count: int = 0
    last_active_at: datetime | None = None
    primary_source_type: Literal["video", "blog"] | None = None
    reliability_score: float | None = None


class AnalystDetail(AnalystSummary):
    sources: list["SourceSummary"] = Field(default_factory=list)
    claims: list["ClaimOut"] = Field(default_factory=list)


class FollowRequest(WireModel):
    followed: bool | None = None


class SourceSummary(WireModel):
    id: str
    type: Literal["video", "blog"]
    url: str
    title: str
    published_at: date | None


class EvaluationOut(WireModel):
    id: str
    verdict: Literal["good", "bad", "ambiguous"] | None
    rationale: str | None
    benchmark: dict[str, Any] | None
    checked_at: datetime


class ClaimOut(WireModel):
    id: str
    source_id: str
    analyst_id: str
    extraction_status: Literal["pending", "complete", "failed"]
    asset_description: str | None
    suggested_ticker: str | None
    condition_trigger: str | None
    expected_outcome: str | None
    horizon: str | None
    timeframe_as_stated: str | None
    target_window_start: date | None
    target_window_end: date | None
    trigger_status: Literal["waiting", "triggered", "expired"] | None
    trigger_observed_at: datetime | None
    trigger_deadline: date | None
    status: Literal["open", "resolved", "expired"]
    evaluations: list[EvaluationOut] = Field(default_factory=list)
    source: SourceSummary
    analyst: "AnalystRef"
    latest_verdict: Literal["good", "bad", "ambiguous"] | None = None
    verdict: Literal["good", "bad", "ambiguous"] | None = None
    resolution: "ResolutionOut | None" = None


class AnalystRef(WireModel):
    id: str
    name: str


class ResolutionOut(WireModel):
    rationale: str
    evaluated_at: datetime
    trade_return_value: float | None = None
    benchmarks: list[dict[str, Any]] = Field(default_factory=list)


class LinkCreate(WireModel):
    url: HttpUrl
    analyst_id: str | None = None
    analyst_name: str | None = Field(default=None, min_length=1, max_length=200)
    force_new: bool = False


class LinkResponse(WireModel):
    status: Literal["requires_analyst_name", "matched", "pending", "review_ready", "created"]
    source_type: Literal["video", "blog"]
    matched_analyst: AnalystSummary | None = None
    analyst: AnalystSummary | None = None
    source_id: str | None = None
    claims: list[ClaimOut] = Field(default_factory=list)
    draft_claims: list[ClaimOut] = Field(default_factory=list)
    message: str | None = None


class ResolutionUpdate(WireModel):
    verdict: Literal["good", "bad", "ambiguous"] | None = None
    rationale: str | None = None
    benchmark: dict[str, Any] | None = None
    status: Literal["open", "resolved", "expired"] = "resolved"
