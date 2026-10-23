"""Durable browser operation handles and exact submission material references."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "ad04c0402601"
down_revision = "ac04c0302601"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_operations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "package_id", sa.Uuid(), sa.ForeignKey("preparation_artifacts.id", ondelete="RESTRICT")
        ),
        sa.Column(
            "research_report_id",
            sa.Uuid(),
            sa.ForeignKey("company_research.id", ondelete="RESTRICT"),
        ),
        sa.Column("reason", sa.String(128)),
    )
    op.create_table(
        "material_submissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.Uuid(),
            sa.ForeignKey("application_events.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "resume_revision_id",
            sa.Uuid(),
            sa.ForeignKey("resume_variant_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "render_artifact_id",
            sa.Uuid(),
            sa.ForeignKey("render_artifacts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "greeting_id", sa.Uuid(), sa.ForeignKey("preparation_artifacts.id", ondelete="RESTRICT")
        ),
        sa.Column(
            "package_id", sa.Uuid(), sa.ForeignKey("preparation_artifacts.id", ondelete="RESTRICT")
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
    )
    op.create_index(
        "ix_material_submissions_application_id", "material_submissions", ["application_id"]
    )


def downgrade():
    op.drop_table("material_submissions")
    op.drop_table("product_operations")
