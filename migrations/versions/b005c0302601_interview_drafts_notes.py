"""Current interview drafts and editable notes; existing frozen sources are unchanged."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b005c0302601"
down_revision = "af05c0202601"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "interview_sessions",
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
    )
    op.add_column("interview_sessions", sa.Column("round_number", sa.Integer()))
    op.add_column("interview_sessions", sa.Column("interview_type", sa.String(20)))
    op.add_column("interview_sessions", sa.Column("context_binding", postgresql.JSONB()))
    op.add_column(
        "knowledge_notes", sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column("knowledge_notes", sa.Column("deleted_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("knowledge_notes", "deleted_at")
    op.drop_column("knowledge_notes", "revision")
    for name in ["context_binding", "interview_type", "round_number", "status"]:
        op.drop_column("interview_sessions", name)
