"""Initial persistent AnalystAudit schema."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gurus",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("followed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("guru_id", sa.String(36), sa.ForeignKey("gurus.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("source_key", sa.String(500), nullable=False),
        sa.Column("youtube_video_id", sa.String(20)),
        sa.Column("youtube_channel_id", sa.String(100)),
        sa.Column("blog_domain", sa.String(253)),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("published_at", sa.Date()),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("ingestion_status", sa.String(20), nullable=False),
        sa.Column("ingestion_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("type IN ('video', 'blog')", name="ck_sources_type"),
        sa.CheckConstraint("ingestion_status IN ('ready', 'failed')", name="ck_sources_ingestion_status"),
        sa.UniqueConstraint("type", "source_key", name="uq_sources_type_source_key"),
    )
    op.create_index("ix_sources_guru_id", "sources", ["guru_id"])
    op.create_index("ix_sources_youtube_channel_id", "sources", ["youtube_channel_id"])
    op.create_index("ix_sources_blog_domain", "sources", ["blog_domain"])
    op.create_table(
        "claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("guru_id", sa.String(36), sa.ForeignKey("gurus.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_status", sa.String(20), nullable=False),
        sa.Column("asset_description", sa.Text()), sa.Column("suggested_ticker", sa.String(30)),
        sa.Column("condition_trigger", sa.Text()), sa.Column("expected_outcome", sa.Text()),
        sa.Column("horizon", sa.String(20)), sa.Column("timeframe_as_stated", sa.Text()),
        sa.Column("target_window_start", sa.Date()), sa.Column("target_window_end", sa.Date()),
        sa.Column("trigger_status", sa.String(20)), sa.Column("trigger_observed_at", sa.DateTime(timezone=True)),
        sa.Column("trigger_deadline", sa.Date()), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('open', 'resolved', 'expired')", name="ck_claims_status"),
        sa.CheckConstraint("extraction_status IN ('pending', 'complete', 'failed')", name="ck_claims_extraction_status"),
        sa.CheckConstraint("trigger_status IN ('waiting', 'triggered', 'expired') OR trigger_status IS NULL", name="ck_claims_trigger_status"),
        sa.CheckConstraint("horizon IN ('short-term', 'swing', 'long-term', 'structural') OR horizon IS NULL", name="ck_claims_horizon"),
        sa.CheckConstraint("target_window_end IS NULL OR target_window_start IS NULL OR target_window_end >= target_window_start", name="ck_claims_target_window_order"),
    )
    op.create_index("ix_claims_guru_status", "claims", ["guru_id", "status"])
    op.create_index("ix_claims_target_window_end", "claims", ["target_window_end"])
    op.create_index("ix_claims_trigger_deadline", "claims", ["trigger_deadline"])
    op.create_table(
        "claim_evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("verdict", sa.String(20)), sa.Column("rationale", sa.Text()),
        sa.Column("benchmark", sa.JSON()), sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("verdict IN ('good', 'bad', 'ambiguous') OR verdict IS NULL", name="ck_claim_evaluations_verdict"),
    )
    op.create_index("ix_claim_evaluations_claim_checked", "claim_evaluations", ["claim_id", "checked_at"])


def downgrade() -> None:
    op.drop_table("claim_evaluations")
    op.drop_table("claims")
    op.drop_table("sources")
    op.drop_table("gurus")
