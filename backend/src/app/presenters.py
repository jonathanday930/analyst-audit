from collections import Counter
from datetime import datetime, time, timezone

from app.db.models import Claim, Guru
from app.schemas import ClaimOut, EvaluationOut, GuruRef, GuruSummary, ResolutionOut, SourceSummary


def guru_summary(guru: Guru) -> GuruSummary:
    resolved = sum(claim.status == "resolved" for claim in guru.claims)
    open_count = sum(claim.status == "open" for claim in guru.claims)
    source_counts = Counter(source.type for source in guru.sources)
    primary = source_counts.most_common(1)[0][0] if source_counts else None
    active_values = [
        datetime.combine(source.published_at, time.min, tzinfo=timezone.utc)
        if source.published_at else source.created_at
        for source in guru.sources
    ]
    return GuruSummary(
        id=guru.id,
        name=guru.name,
        followed=guru.followed,
        claim_count=len(guru.claims),
        resolved_count=resolved,
        open_count=open_count,
        last_active_at=max(active_values) if active_values else None,
        primary_source_type=primary,
        reliability_score=None,
    )


def claim_out(claim: Claim) -> ClaimOut:
    evaluations = [EvaluationOut.model_validate(value) for value in claim.evaluations]
    latest = evaluations[-1] if evaluations else None
    benchmark = latest.benchmark if latest and latest.benchmark else {}
    resolution = None
    if latest:
        resolution = ResolutionOut(
            rationale=latest.rationale or "",
            evaluated_at=latest.checked_at,
            trade_return_value=benchmark.get("trade_return_value"),
            benchmarks=benchmark.get("benchmarks", []),
        )
    return ClaimOut(
        id=claim.id,
        source_id=claim.source_id,
        guru_id=claim.guru_id,
        extraction_status=claim.extraction_status,
        asset_description=claim.asset_description,
        suggested_ticker=claim.suggested_ticker,
        condition_trigger=claim.condition_trigger,
        expected_outcome=claim.expected_outcome,
        horizon=claim.horizon,
        timeframe_as_stated=claim.timeframe_as_stated,
        target_window_start=claim.target_window_start,
        target_window_end=claim.target_window_end,
        trigger_status=claim.trigger_status,
        trigger_observed_at=claim.trigger_observed_at,
        trigger_deadline=claim.trigger_deadline,
        status=claim.status,
        evaluations=evaluations,
        source=SourceSummary.model_validate(claim.source),
        guru=GuruRef(id=claim.guru.id, name=claim.guru.name),
        latest_verdict=latest.verdict if latest else None,
        verdict=latest.verdict if latest else None,
        resolution=resolution,
    )
