"""Hide closed applications without removing historical references."""

import sqlalchemy as sa
from alembic import op

revision = "ba05c1302601"
down_revision = "b905c1202601"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "applications", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade():
    # Do not silently resurrect deleted applications when rolling back the schema.
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS(SELECT 1 FROM applications WHERE deleted_at IS NOT NULL)"))
        .scalar()
    ):
        raise RuntimeError("application_deletion_history_requires_retention")
    op.drop_column("applications", "deleted_at")
