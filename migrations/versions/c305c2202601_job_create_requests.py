"""Durable request identity for Job and Application creation; no historical backfill."""

import sqlalchemy as sa
from alembic import op

revision = "c305c2202601"
down_revision = "c205c2102601"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_create_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("job_postings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM job_create_requests)")):
        raise RuntimeError("job_create_request_history_requires_retention")
    op.drop_table("job_create_requests")
