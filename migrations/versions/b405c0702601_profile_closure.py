"""Profile creation intents and saved resume source evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "b405c0702601"
down_revision = "b305c0602601"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("profile_records", sa.Column("request_id", sa.Uuid()))
    op.create_unique_constraint("uq_profile_records_request_id", "profile_records", ["request_id"])
    op.add_column("resume_workspaces", sa.Column("content_sources", pg.JSONB()))


def downgrade():
    op.drop_column("resume_workspaces", "content_sources")
    op.drop_constraint("uq_profile_records_request_id", "profile_records", type_="unique")
    op.drop_column("profile_records", "request_id")
