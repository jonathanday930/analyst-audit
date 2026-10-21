from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Analyst(Base):
    __tablename__ = "analysts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    followed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    sources: Mapped[list[Source]] = relationship(back_populates="analyst", cascade="all, delete-orphan")
    claims: Mapped[list[Claim]] = relationship(back_populates="analyst", cascade="all, delete-orphan")
    stances: Mapped[list[Stance]] = relationship(back_populates="analyst", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("type IN ('video', 'blog')", name="ck_sources_type"),
        CheckConstraint("ingestion_status IN ('ready', 'failed')", name="ck_sources_ingestion_status"),
        UniqueConstraint("type", "source_key", name="uq_sources_type_source_key"),
        Index("ix_sources_analyst_id", "analyst_id"),
        Index("ix_sources_youtube_channel_id", "youtube_channel_id"),
        Index("ix_sources_blog_domain", "blog_domain"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    analyst_id: Mapped[str] = mapped_column(ForeignKey("analysts.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_key: Mapped[str] = mapped_column(String(500), nullable=False)
    youtube_video_id: Mapped[str | None] = mapped_column(String(20))
    youtube_channel_id: Mapped[str | None] = mapped_column(String(100))
    blog_domain: Mapped[str | None] = mapped_column(String(253))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[date | None] = mapped_column(Date)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    ingestion_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ready")
    ingestion_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    analyst: Mapped[Analyst] = relationship(back_populates="sources")
    claims: Mapped[list[Claim]] = relationship(back_populates="source", cascade="all, delete-orphan")
    stances: Mapped[list[Stance]] = relationship(back_populates="source", cascade="all, delete-orphan")


class Stance(Base):
    __tablename__ = "stances"
    __table_args__ = (
        CheckConstraint("kind IN ('position', 'sentiment')", name="ck_stances_kind"),
        CheckConstraint("direction IN ('long', 'short', 'exited') OR direction IS NULL", name="ck_stances_direction"),
        CheckConstraint("sentiment IN ('bullish', 'neutral', 'bearish', 'uncertain') OR sentiment IS NULL", name="ck_stances_sentiment"),
        Index("ix_stances_analyst_stated", "analyst_id", "stated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    analyst_id: Mapped[str] = mapped_column(ForeignKey("analysts.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    asset_description: Mapped[str | None] = mapped_column(Text)
    suggested_ticker: Mapped[str | None] = mapped_column(String(20))
    direction: Mapped[str | None] = mapped_column(String(20))
    sentiment: Mapped[str | None] = mapped_column(String(20))
    scope: Mapped[str | None] = mapped_column(Text)
    supporting_quotes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    stated_at: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    analyst: Mapped[Analyst] = relationship(back_populates="stances")
    source: Mapped[Source] = relationship(back_populates="stances")


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'resolved', 'expired')", name="ck_claims_status"),
        CheckConstraint("extraction_status IN ('pending', 'complete', 'failed')", name="ck_claims_extraction_status"),
        CheckConstraint("trigger_status IN ('waiting', 'triggered', 'expired') OR trigger_status IS NULL", name="ck_claims_trigger_status"),
        CheckConstraint("horizon IN ('short-term', 'swing', 'long-term', 'structural') OR horizon IS NULL", name="ck_claims_horizon"),
        Index("ix_claims_analyst_status", "analyst_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    analyst_id: Mapped[str] = mapped_column(ForeignKey("analysts.id", ondelete="CASCADE"), nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    asset_description: Mapped[str | None] = mapped_column(Text)
    suggested_ticker: Mapped[list[str] | None] = mapped_column(JSON)
    condition_trigger: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    claim: Mapped[str | None] = mapped_column(Text)
    stated_implication: Mapped[str | None] = mapped_column(Text)
    grounds: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    warrant: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    backing: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    qualifier: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    rebuttal_invalidation: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    horizon: Mapped[str | None] = mapped_column(String(20))
    trigger_status: Mapped[str | None] = mapped_column(String(20))
    trigger_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    source: Mapped[Source] = relationship(back_populates="claims")
    analyst: Mapped[Analyst] = relationship(back_populates="claims")
    evaluations: Mapped[list[ClaimEvaluation]] = relationship(back_populates="claim", cascade="all, delete-orphan", order_by="ClaimEvaluation.checked_at")


class ClaimEvaluation(Base):
    __tablename__ = "claim_evaluations"
    __table_args__ = (
        CheckConstraint("verdict IN ('good', 'bad', 'ambiguous') OR verdict IS NULL", name="ck_claim_evaluations_verdict"),
        Index("ix_claim_evaluations_claim_checked", "claim_id", "checked_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    verdict: Mapped[str | None] = mapped_column(String(20))
    rationale: Mapped[str | None] = mapped_column(Text)
    benchmark: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    claim: Mapped[Claim] = relationship(back_populates="evaluations")
