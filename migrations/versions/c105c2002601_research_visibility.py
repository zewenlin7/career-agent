"""Company-wide research visibility; retain reports, evidence and audit references."""

import sqlalchemy as sa
from alembic import op

revision = "c105c2002601"
down_revision = "c005c1902601"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_research", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM company_research WHERE deleted_at IS NOT NULL")
    ):
        raise RuntimeError("research_visibility_requires_retention")
    op.drop_column("company_research", "deleted_at")
