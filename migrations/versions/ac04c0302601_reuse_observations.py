"""Exact search observation persistence and nullable Debrief create identity."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "ac04c0302601"
down_revision = "ab04c0202601"
branch_labels = None
depends_on = None


def common():
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    ]


def upgrade():
    op.create_table(
        "search_observations",
        *common(),
        sa.Column("identity_hash", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
    )
    op.create_index(
        "ix_search_observations_identity_hash", "search_observations", ["identity_hash"]
    )
    op.create_table(
        "reuse_decisions",
        *common(),
        sa.Column("run_id", sa.Uuid()),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("operation", sa.String(128), nullable=False),
        sa.Column("disposition", sa.String(20), nullable=False),
        sa.Column("identity_hash", sa.String(64)),
        sa.Column("observation_id", sa.Uuid()),
    )
    op.create_index("ix_reuse_decisions_run_id", "reuse_decisions", ["run_id"])
    op.create_index("ix_reuse_decisions_identity_hash", "reuse_decisions", ["identity_hash"])
    op.add_column("debrief_runs", sa.Column("request_fingerprint", sa.String(64)))
    op.create_unique_constraint(
        "uq_debrief_runs_request_fingerprint", "debrief_runs", ["request_fingerprint"]
    )


def downgrade():
    op.drop_constraint("uq_debrief_runs_request_fingerprint", "debrief_runs", type_="unique")
    op.drop_column("debrief_runs", "request_fingerprint")
    op.drop_table("reuse_decisions")
    op.drop_table("search_observations")
