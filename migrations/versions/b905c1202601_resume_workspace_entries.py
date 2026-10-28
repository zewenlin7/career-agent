"""Keep ordinary editing workspaces in the same user-visible library entry."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b905c1202601"
down_revision = "b805c1102601"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "resume_workspaces",
        sa.Column("library_state", postgresql.JSONB(), nullable=False, server_default="{}"),
    )


def downgrade():
    op.drop_column("resume_workspaces", "library_state")
