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
    categories: list["AnalystCategory"] = Field(default_factory=list)


class AnalystCategory(WireModel):
    label: str
    score: float | None = None
    claim_count: int = 0
    resolved_count: int = 0


class AnalystDetail(AnalystSummary):
    sources: list["SourceSummary"] = Field(default_factory=list)
    claims: list["ClaimOut"] = Field(default_factory=list)
    stances: list["StanceOut"] = Field(default_factory=list)
    overall_summary: str | None = None
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    consistency_notes: str | None = None


class FollowRequest(WireModel):
    followed: bool | None = None


class SourceSummary(WireModel):
    id: str
    type: Literal["video", "blog"]
    url: str
    title: str
    published_at: date | None


class StanceSnapshotOut(WireModel):
    ticker: str
    call_date: date
    as_of: date
    days_since_call: int
    call_price: float
    current_price: float
    high_since_call: float
    high_date: date
    low_since_call: float
    low_date: date
    change_since_call_pct: float


class StanceOut(WireModel):
    id: str
    analyst_id: str
    source_id: str
    kind: Literal["position", "sentiment"]
    asset_description: str | None
    suggested_ticker: str | None
    direction: Literal["long", "short", "exited"] | None
    sentiment: Literal["bullish", "neutral", "bearish", "uncertain"] | None
    scope: str | None
    supporting_quotes: list[str]
    stated_at: date | None
    source: SourceSummary
    snapshot: StanceSnapshotOut | None = None


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
    suggested_ticker: list[str] | None
    condition_trigger: list[str]
    claim: str | None
    stated_implication: str | None
    grounds: list[str]
    warrant: list[str]
    backing: list[str]
    qualifier: str | None
    confidence: float | None
    rebuttal_invalidation: list[str]
    horizon: str | None
    trigger_status: Literal["waiting", "triggered", "expired"] | None
    trigger_observed_at: datetime | None
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
