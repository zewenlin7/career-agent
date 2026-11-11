"""Explicit Mock ownership and idempotent creation; legacy ownership remains unknown."""

import sqlalchemy as sa
from alembic import op

revision = "c005c1902601"
down_revision = "bf05c1802601"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mock_interview_sessions", sa.Column("application_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_mock_interview_sessions_application_id_applications",
        "mock_interview_sessions",
        "applications",
        ["application_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_mock_interview_sessions_application_id", "mock_interview_sessions", ["application_id"]
    )
    op.add_column("mock_interview_sessions", sa.Column("request_id", sa.Uuid(), nullable=True))
    op.add_column(
        "mock_interview_sessions", sa.Column("request_hash", sa.String(64), nullable=True)
    )
    op.create_unique_constraint(
        "uq_mock_interview_sessions_request_id", "mock_interview_sessions", ["request_id"]
    )


def downgrade():
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS(SELECT 1 FROM mock_interview_sessions "
                "WHERE application_id IS NOT NULL"
                " OR request_id IS NOT NULL)"
            )
        )
        .scalar()
    ):
        raise RuntimeError("mock_creation_identity_requires_retention")
    op.drop_constraint(
        "uq_mock_interview_sessions_request_id", "mock_interview_sessions", type_="unique"
    )
    op.drop_column("mock_interview_sessions", "request_hash")
    op.drop_column("mock_interview_sessions", "request_id")
    op.drop_index("ix_mock_interview_sessions_application_id", "mock_interview_sessions")
    op.drop_constraint(
        "fk_mock_interview_sessions_application_id_applications",
        "mock_interview_sessions",
        type_="foreignkey",
    )
    op.drop_column("mock_interview_sessions", "application_id")
