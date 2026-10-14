"""Persist tool schema versions; historical unknown versions stay null."""

import sqlalchemy as sa
from alembic import op

revision = "f730b2c01231"
down_revision = "e620a1b90120"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tool_calls", sa.Column("input_schema_version", sa.String(128), nullable=True))
    op.add_column("tool_calls", sa.Column("output_schema_version", sa.String(128), nullable=True))


def downgrade():
    op.drop_column("tool_calls", "output_schema_version")
    op.drop_column("tool_calls", "input_schema_version")
