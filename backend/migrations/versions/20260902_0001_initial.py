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
        "analysts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("followed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("analyst_id", sa.String(36), sa.ForeignKey("analysts.id", ondelete="CASCADE"), nullable=False),
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
    op.create_index("ix_sources_analyst_id", "sources", ["analyst_id"])
    op.create_index("ix_sources_youtube_channel_id", "sources", ["youtube_channel_id"])
    op.create_index("ix_sources_blog_domain", "sources", ["blog_domain"])
    op.create_table(
        "stances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("analyst_id", sa.String(36), sa.ForeignKey("analysts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("asset_description", sa.Text()),
        sa.Column("suggested_ticker", sa.String(20)),
        sa.Column("direction", sa.String(20)),
        sa.Column("sentiment", sa.String(20)),
        sa.Column("scope", sa.Text()),
        sa.Column("supporting_quotes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("stated_at", sa.Date()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('position', 'sentiment')", name="ck_stances_kind"),
        sa.CheckConstraint("direction IN ('long', 'short', 'exited') OR direction IS NULL", name="ck_stances_direction"),
        sa.CheckConstraint("sentiment IN ('bullish', 'neutral', 'bearish', 'uncertain') OR sentiment IS NULL", name="ck_stances_sentiment"),
    )
    op.create_index("ix_stances_analyst_stated", "stances", ["analyst_id", "stated_at"])
    op.create_table(
        "claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analyst_id", sa.String(36), sa.ForeignKey("analysts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_status", sa.String(20), nullable=False),
        sa.Column("asset_description", sa.Text()), sa.Column("suggested_ticker", sa.JSON()),
        sa.Column("condition_trigger", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("claim", sa.Text()), sa.Column("stated_implication", sa.Text()),
        sa.Column("grounds", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("warrant", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("backing", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("qualifier", sa.Text()), sa.Column("confidence", sa.Float()),
        sa.Column("rebuttal_invalidation", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("horizon", sa.String(20)),
        sa.Column("trigger_status", sa.String(20)), sa.Column("trigger_observed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('open', 'resolved', 'expired')", name="ck_claims_status"),
        sa.CheckConstraint("extraction_status IN ('pending', 'complete', 'failed')", name="ck_claims_extraction_status"),
        sa.CheckConstraint("trigger_status IN ('waiting', 'triggered', 'expired') OR trigger_status IS NULL", name="ck_claims_trigger_status"),
        sa.CheckConstraint("horizon IN ('short-term', 'swing', 'long-term', 'structural') OR horizon IS NULL", name="ck_claims_horizon"),
    )
    op.create_index("ix_claims_analyst_status", "claims", ["analyst_id", "status"])
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
    op.drop_table("stances")
    op.drop_table("claims")
    op.drop_table("sources")
    op.drop_table("analysts")
