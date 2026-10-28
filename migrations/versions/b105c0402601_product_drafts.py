"""Private reviewable draft ownership with accepted-call provenance."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b105c0402601"
down_revision = "b005c0302601"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "resume_variants",
        sa.Column("library_visible", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_table(
        "product_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("agent_runs.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("logical_operation_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("task", sa.String(80), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(128)),
        *[
            sa.Column(name, postgresql.JSONB(), nullable=False)
            for name in ["request", "context", "usage", "limits"]
        ],
        sa.Column("output", postgresql.JSONB()),
        sa.Column("adopted", postgresql.JSONB()),
        sa.Column(
            "accepted_model_call_id",
            sa.Uuid(),
            sa.ForeignKey("model_calls.id", ondelete="RESTRICT"),
        ),
    )


def downgrade():
    op.drop_column("resume_variants", "library_visible")
    op.drop_table("product_drafts")
