"""Private preparation artifacts and company-scoped research cache."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c38190f12a01"
down_revision = "ade973186357"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tool_calls", sa.Column("usage", postgresql.JSONB(), nullable=True))
    op.add_column(
        "job_requirements", sa.Column("extraction_metadata", postgresql.JSONB(), nullable=True)
    )
    op.create_table(
        "company_research",
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("research_version", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "research_version"),
        sa.CheckConstraint("research_version > 0", name="positive_version"),
    )
    op.create_index("ix_company_research_company_id", "company_research", ["company_id"])
    op.create_table(
        "preparation_artifacts",
        sa.Column(
            "run_id", sa.Uuid(), sa.ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "job_revision_id",
            sa.Uuid(),
            sa.ForeignKey("job_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("personal_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_preparation_artifacts_run_id", "preparation_artifacts", ["run_id"])


def downgrade() -> None:
    op.drop_table("preparation_artifacts")
    op.drop_table("company_research")
    op.drop_column("job_requirements", "extraction_metadata")
    op.drop_column("tool_calls", "usage")
