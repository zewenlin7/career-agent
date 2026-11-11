"""Retain exact generated artifacts while hiding unused Greeting records."""

import sqlalchemy as sa
from alembic import op

revision = "bd05c1602601"
down_revision = "bc05c1502601"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_result_removals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            sa.Uuid(),
            sa.ForeignKey("preparation_artifacts.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("request_id", sa.Uuid(), nullable=False, unique=True),
    )


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS(SELECT 1 FROM product_result_removals)"))
        .scalar()
    ):
        raise RuntimeError("result_removal_history_requires_retention")
    op.drop_table("product_result_removals")
