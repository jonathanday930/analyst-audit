from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Claim, ClaimEvaluation, Guru, Source


def create_guru(db: Session, *, name: str, followed: bool = True) -> Guru:
    guru = Guru(name=name.strip(), followed=followed)
    db.add(guru)
    db.flush()
    return guru


def list_gurus(db: Session, *, followed: bool | None = None) -> list[Guru]:
    stmt: Select[tuple[Guru]] = select(Guru).order_by(Guru.name)
    if followed is not None:
        stmt = stmt.where(Guru.followed == followed)
    return list(db.scalars(stmt))


def get_guru(db: Session, guru_id: str) -> Guru | None:
    return db.scalar(
        select(Guru)
        .where(Guru.id == guru_id)
        .options(selectinload(Guru.sources), selectinload(Guru.claims).selectinload(Claim.evaluations))
    )


def find_guru_for_source(db: Session, *, source_type: str, identity: str) -> Guru | None:
    identity_column = Source.youtube_channel_id if source_type == "video" else Source.blog_domain
    return db.scalar(select(Guru).join(Source).where(identity_column == identity).limit(1))


def find_source(db: Session, *, source_type: str, source_key: str) -> Source | None:
    return db.scalar(select(Source).where(Source.type == source_type, Source.source_key == source_key))


def create_source_with_placeholder(
    db: Session,
    *,
    guru: Guru,
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
        guru=guru,
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
    claim = Claim(guru=guru, source=source, extraction_status="pending", status="open")
    db.add_all([source, claim])
    db.flush()
    return source, claim


def list_claims(
    db: Session,
    *,
    status: str | None = None,
    verdict: str | None = None,
    guru_id: str | None = None,
) -> list[Claim]:
    stmt = select(Claim).options(
        selectinload(Claim.evaluations), selectinload(Claim.source), selectinload(Claim.guru)
    ).order_by(Claim.created_at.desc())
    if status:
        stmt = stmt.where(Claim.status == status)
    if guru_id:
        stmt = stmt.where(Claim.guru_id == guru_id)
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
            selectinload(Claim.evaluations), selectinload(Claim.source), selectinload(Claim.guru)
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
) -> Claim:
    claim.status = status
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
