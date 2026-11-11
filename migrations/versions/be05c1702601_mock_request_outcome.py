"""Freeze metadata-only Mock request outcomes for cross-page status reads."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "be05c1702601"
down_revision = "bd05c1602601"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mock_request_receipts", sa.Column("outcome", postgresql.JSONB(), nullable=True))


def downgrade():
    if (
        op.get_bind()
        .execute(
            sa.text("SELECT EXISTS(SELECT 1 FROM mock_request_receipts WHERE outcome IS NOT NULL)")
        )
        .scalar()
    ):
        raise RuntimeError("mock_request_history_requires_retention")
    op.drop_column("mock_request_receipts", "outcome")
