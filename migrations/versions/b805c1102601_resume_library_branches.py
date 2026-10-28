"""Persistent naming branches and user-visible resume entry replacement."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b805c1102601"
down_revision = "b705c1002601"
branch_labels = None
depends_on = None


def trigger(extra):
    fields = "'display_name','metadata_revision','archived_at','saved_at','presentation'" + extra
    op.execute(f"""CREATE OR REPLACE FUNCTION prevent_resume_revision_update() RETURNS trigger AS $$
        BEGIN
        IF (to_jsonb(NEW) - ARRAY[{fields}]) IS DISTINCT FROM (to_jsonb(OLD) - ARRAY[{fields}]) THEN
            RAISE EXCEPTION 'resume_revision_immutable';
        END IF;
        RETURN NEW;
        END; $$ LANGUAGE plpgsql""")


def upgrade():
    trigger(",'library_state'")
    op.add_column(
        "resume_variant_revisions",
        sa.Column("library_state", postgresql.JSONB(), nullable=False, server_default="{}"),
    )


def downgrade():
    trigger("")
    op.drop_column("resume_variant_revisions", "library_state")
