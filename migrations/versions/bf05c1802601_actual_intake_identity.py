"""Add optional intake identity without rewriting historical interviews."""

import sqlalchemy as sa
from alembic import op

revision = "bf05c1802601"
down_revision = "be05c1702601"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("interview_sessions", sa.Column("request_id", sa.Uuid(), nullable=True))
    op.add_column("interview_sessions", sa.Column("request_hash", sa.String(64), nullable=True))
    op.add_column(
        "interview_sessions", sa.Column("saved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint(
        "uq_interview_sessions_request_id", "interview_sessions", ["request_id"]
    )


def downgrade():
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS(SELECT 1 FROM interview_sessions WHERE request_id IS NOT NULL"
                " OR saved_at IS NOT NULL)"
            )
        )
        .scalar()
    ):
        raise RuntimeError("interview_intake_identity_requires_retention")
    op.drop_constraint("uq_interview_sessions_request_id", "interview_sessions", type_="unique")
    op.drop_column("interview_sessions", "saved_at")
    op.drop_column("interview_sessions", "request_hash")
    op.drop_column("interview_sessions", "request_id")
