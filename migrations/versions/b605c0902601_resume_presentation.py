"""Separate presentation state and truthful save timestamps."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "b605c0902601"
down_revision = "b505c0802601"
branch_labels = None
depends_on = None


def trigger(extra):
    fields = "'display_name','metadata_revision','archived_at'" + extra
    op.execute(f"""CREATE OR REPLACE FUNCTION prevent_resume_revision_update() RETURNS trigger AS $$
        BEGIN
        IF (to_jsonb(NEW) - ARRAY[{fields}]) IS DISTINCT FROM (to_jsonb(OLD) - ARRAY[{fields}]) THEN
            RAISE EXCEPTION 'resume_revision_immutable';
        END IF;
        RETURN NEW;
        END; $$ LANGUAGE plpgsql""")


def upgrade():
    trigger(",'saved_at','presentation'")
    for table in ("profile_records", "resume_workspaces", "resume_variant_revisions"):
        op.add_column(table, sa.Column("saved_at", sa.DateTime(timezone=True), nullable=True))
    for table in ("resume_workspaces", "resume_variant_revisions"):
        op.add_column(
            table, sa.Column("presentation", pg.JSONB(), nullable=False, server_default="{}")
        )


def downgrade():
    trigger("")
    for table in ("resume_workspaces", "resume_variant_revisions"):
        op.drop_column(table, "presentation")
    for table in ("profile_records", "resume_workspaces", "resume_variant_revisions"):
        op.drop_column(table, "saved_at")
