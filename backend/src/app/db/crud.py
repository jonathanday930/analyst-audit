from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Claim, ClaimEvaluation, Analyst, Source, Stance


def create_analyst(db: Session, *, name: str, followed: bool = True) -> Analyst:
    analyst = Analyst(name=name.strip(), followed=followed)
    db.add(analyst)
    db.flush()
    return analyst


def list_analysts(db: Session, *, followed: bool | None = None) -> list[Analyst]:
    stmt: Select[tuple[Analyst]] = select(Analyst).order_by(Analyst.name)
    if followed is not None:
        stmt = stmt.where(Analyst.followed == followed)
    return list(db.scalars(stmt))


def get_analyst(db: Session, analyst_id: str) -> Analyst | None:
    return db.scalar(
        select(Analyst)
        .where(Analyst.id == analyst_id)
        .options(
            selectinload(Analyst.sources),
            selectinload(Analyst.claims).selectinload(Claim.evaluations),
            selectinload(Analyst.stances).selectinload(Stance.source),
        )
    )


def find_analyst_for_source(db: Session, *, source_type: str, identity: str) -> Analyst | None:
    identity_column = Source.youtube_channel_id if source_type == "video" else Source.blog_domain
    return db.scalar(select(Analyst).join(Source).where(identity_column == identity).limit(1))


def find_source(db: Session, *, source_type: str, source_key: str) -> Source | None:
    return db.scalar(select(Source).where(Source.type == source_type, Source.source_key == source_key))


def create_source_with_placeholder(
    db: Session,
    *,
    analyst: Analyst,
    source_type: str,
    url: str,
    canonical_url: str,
    source_key: str,
    title: str,
    content: str,
    published_at: date | None = None,
    youtube_video_id: str | None = None,
    youtube_channel_id: str | None = None,
    blog_domain: str | None = None,
) -> tuple[Source, Claim]:
    source = Source(
        analyst=analyst,
        type=source_type,
        url=url,
        canonical_url=canonical_url,
        source_key=source_key,
        title=title,
        content=content,
        published_at=published_at,
        youtube_video_id=youtube_video_id,
        youtube_channel_id=youtube_channel_id,
        blog_domain=blog_domain,
        ingestion_status="ready",
    )
    claim = Claim(analyst=analyst, source=source, extraction_status="pending", status="open")
    db.add_all([source, claim])
    db.flush()
    return source, claim


def list_stances(db: Session, *, analyst_id: str | None = None) -> list[Stance]:
    stmt = select(Stance).options(selectinload(Stance.source)).order_by(Stance.stated_at.desc(), Stance.created_at.desc())
    if analyst_id:
        stmt = stmt.where(Stance.analyst_id == analyst_id)
    return list(db.scalars(stmt).unique())


def create_stance(db: Session, *, analyst: Analyst, source: Source, extraction: Any) -> Stance:
    stance = Stance(
        analyst=analyst,
        source=source,
        kind=extraction.kind,
        asset_description=extraction.asset_description,
        suggested_ticker=extraction.suggested_ticker,
        direction=extraction.direction,
        sentiment=extraction.sentiment,
        scope=extraction.scope,
        supporting_quotes=extraction.supporting_quotes,
        stated_at=source.published_at,
    )
    db.add(stance)
    db.flush()
    return stance


def replace_source_claims(db: Session, *, source: Source, extractions: list[Any]) -> list[Claim]:
    for claim in list(source.claims):
        db.delete(claim)
    db.flush()
    claims = [Claim(
        source=source, analyst_id=source.analyst_id, extraction_status="complete",
        asset_description=item.asset_description, suggested_ticker=item.suggested_ticker,
        condition_trigger=item.condition_trigger, claim=item.claim,
        stated_implication=item.stated_implication, grounds=item.grounds, warrant=item.warrant,
        backing=item.backing, qualifier=item.qualifier, confidence=item.confidence,
        rebuttal_invalidation=item.rebuttal_invalidation, horizon=item.horizon, status="open",
    ) for item in extractions]
    db.add_all(claims)
    db.flush()
    return claims


def list_claims(
    db: Session,
    *,
    status: str | None = None,
    verdict: str | None = None,
    analyst_id: str | None = None,
) -> list[Claim]:
    stmt = select(Claim).options(
        selectinload(Claim.evaluations), selectinload(Claim.source), selectinload(Claim.analyst)
    ).order_by(Claim.created_at.desc())
    if status:
        stmt = stmt.where(Claim.status == status)
    if analyst_id:
        stmt = stmt.where(Claim.analyst_id == analyst_id)
    if verdict:
        ranked = select(
            ClaimEvaluation.claim_id,
            ClaimEvaluation.verdict,
            func.row_number().over(
                partition_by=ClaimEvaluation.claim_id,
                order_by=(ClaimEvaluation.checked_at.desc(), ClaimEvaluation.id.desc()),
            ).label("position"),
        ).subquery()
        stmt = stmt.join(ranked, ranked.c.claim_id == Claim.id).where(
            ranked.c.position == 1,
            ranked.c.verdict == verdict,
        )
    return list(db.scalars(stmt).unique())


def get_claim(db: Session, claim_id: str) -> Claim | None:
    return db.scalar(
        select(Claim).where(Claim.id == claim_id).options(
            selectinload(Claim.evaluations), selectinload(Claim.source), selectinload(Claim.analyst)
        )
    )


def update_claim_resolution(
    db: Session,
    *,
    claim: Claim,
    verdict: str | None,
    rationale: str | None,
    benchmark: dict[str, Any] | None = None,
    status: str = "resolved",
    checked_at: datetime | None = None,
    trigger_status: str | None = None,
    trigger_observed_at: datetime | None = None,
) -> Claim:
    claim.status = status
    if trigger_status is not None:
        claim.trigger_status = trigger_status
    if trigger_observed_at is not None:
        claim.trigger_observed_at = trigger_observed_at
    evaluation = ClaimEvaluation(
        claim=claim,
        verdict=verdict,
        rationale=rationale,
        benchmark=benchmark,
        **({"checked_at": checked_at} if checked_at else {}),
    )
    db.add(evaluation)
    db.flush()
    return claim
