"""Persist isolated named Profile editing sessions without changing snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "b505c0802601"
down_revision = "b405c0702601"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("profile_records", sa.Column("editing", pg.JSONB(), nullable=True))


def downgrade():
    op.drop_column("profile_records", "editing")
