from collections import Counter
from datetime import date, datetime, time, timezone

from app.config import get_settings
from app.db.models import Claim, Analyst
from app.llm.meta_analyst import analyze_analyst
from app.llm.schemas import AnalystMetaAnalysis, ClaimHistoryEntry, StanceExtraction, StanceHistoryEntry
from app.prices.stance_snapshot import compute_stance_snapshot, resolve_stance_ticker
from app.schemas import AnalystCategory, ClaimOut, EvaluationOut, AnalystRef, AnalystSummary, ResolutionOut, SourceSummary, StanceOut, StanceSnapshotOut


def _latest_verdict(claim: Claim) -> str | None:
    return claim.evaluations[-1].verdict if claim.evaluations else None


def meta_analysis(analyst: Analyst) -> AnalystMetaAnalysis | None:
    """Return stage-3 analysis when configured; API reads remain usable without an LLM key."""
    if not get_settings().anthropic_api_key or not analyst.claims:
        return None
    claims = [ClaimHistoryEntry(
        claim_id=claim.id,
        asset_description=claim.asset_description or "unspecified asset",
        claim=claim.claim or "pending extraction",
        horizon=claim.horizon or "swing",
        status=claim.status,
        verdict=_latest_verdict(claim),
        rationale=claim.evaluations[-1].rationale if claim.evaluations else None,
    ) for claim in analyst.claims]
    stances = [StanceHistoryEntry(
        kind=stance.kind,
        asset_description=stance.asset_description,
        direction=stance.direction,
        sentiment=stance.sentiment,
        scope=stance.scope,
        quotes=stance.supporting_quotes,
        stated_at=stance.stated_at,
    ) for stance in analyst.stances]
    try:
        return analyze_analyst(analyst_name=analyst.name, claims=claims, stances=stances)
    except Exception:
        return None


def category_scores(analyst: Analyst, analysis: AnalystMetaAnalysis | None) -> list[AnalystCategory]:
    if not analysis:
        return []
    by_id = {item.claim_id: item.category for item in analysis.categorizations}
    grouped: dict[str, list[str]] = {}
    for claim in analyst.claims:
        category = by_id.get(claim.id)
        if category:
            grouped.setdefault(category, []).append(_latest_verdict(claim) or "unresolved")
    result = []
    for label, verdicts in sorted(grouped.items()):
        graded = [verdict for verdict in verdicts if verdict in {"good", "bad"}]
        result.append(AnalystCategory(
            label=label,
            score=round(graded.count("good") / len(graded) * 100, 1) if graded else None,
            claim_count=len(verdicts),
            resolved_count=len(graded),
        ))
    return result


def analyst_summary(analyst: Analyst, *, analysis: AnalystMetaAnalysis | None = None) -> AnalystSummary:
    resolved = sum(claim.status == "resolved" for claim in analyst.claims)
    open_count = sum(claim.status == "open" for claim in analyst.claims)
    source_counts = Counter(source.type for source in analyst.sources)
    primary = source_counts.most_common(1)[0][0] if source_counts else None
    active_values = [
        datetime.combine(source.published_at, time.min, tzinfo=timezone.utc)
        if source.published_at else source.created_at
        for source in analyst.sources
    ]
    analysis = analysis if analysis is not None else meta_analysis(analyst)
    return AnalystSummary(
        id=analyst.id,
        name=analyst.name,
        followed=analyst.followed,
        claim_count=len(analyst.claims),
        resolved_count=resolved,
        open_count=open_count,
        last_active_at=max(active_values) if active_values else None,
        primary_source_type=primary,
        reliability_score=reliability_score(analyst),
        categories=category_scores(analyst, analysis),
    )


def reliability_score(analyst: Analyst) -> float | None:
    verdicts = [evaluation.verdict for claim in analyst.claims for evaluation in claim.evaluations]
    verdicts = [verdict for verdict in verdicts if verdict in {"good", "bad"}]
    if not verdicts:
        return None
    return round(sum(verdict == "good" for verdict in verdicts) / len(verdicts) * 100, 1)


def stance_out(stance) -> StanceOut:
    snapshot = None
    if stance.source.published_at:
        extraction = StanceExtraction(
            kind=stance.kind,
            asset_description=stance.asset_description,
            suggested_ticker=stance.suggested_ticker,
            direction=stance.direction,
            sentiment=stance.sentiment,
            scope=stance.scope,
            supporting_quotes=stance.supporting_quotes,
        )
        ticker = resolve_stance_ticker(extraction)
        if ticker:
            computed = compute_stance_snapshot(ticker=ticker, call_date=stance.source.published_at, as_of=date.today())
            if computed:
                snapshot = StanceSnapshotOut.model_validate(computed)
    return StanceOut(
        id=stance.id,
        analyst_id=stance.analyst_id,
        source_id=stance.source_id,
        kind=stance.kind,
        asset_description=stance.asset_description,
        suggested_ticker=stance.suggested_ticker,
        direction=stance.direction,
        sentiment=stance.sentiment,
        scope=stance.scope,
        supporting_quotes=stance.supporting_quotes,
        stated_at=stance.stated_at,
        source=SourceSummary.model_validate(stance.source),
        snapshot=snapshot,
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
        analyst_id=claim.analyst_id,
        extraction_status=claim.extraction_status,
        asset_description=claim.asset_description,
        suggested_ticker=claim.suggested_ticker,
        condition_trigger=claim.condition_trigger,
        claim=claim.claim,
        stated_implication=claim.stated_implication,
        grounds=claim.grounds,
        warrant=claim.warrant,
        backing=claim.backing,
        qualifier=claim.qualifier,
        confidence=claim.confidence,
        rebuttal_invalidation=claim.rebuttal_invalidation,
        horizon=claim.horizon,
        trigger_status=claim.trigger_status,
        trigger_observed_at=claim.trigger_observed_at,
        status=claim.status,
        evaluations=evaluations,
        source=SourceSummary.model_validate(claim.source),
        analyst=AnalystRef(id=claim.analyst.id, name=claim.analyst.name),
        latest_verdict=latest.verdict if latest else None,
        verdict=latest.verdict if latest else None,
        resolution=resolution,
    )
