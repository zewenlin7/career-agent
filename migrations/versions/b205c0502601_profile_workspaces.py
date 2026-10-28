"""Editable Profile/Resume workspaces; archival metadata never deletes provenance."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "b205c0502601"
down_revision = "b105c0402601"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TRIGGER resume_revision_immutable ON resume_variant_revisions")
    for table in ["personal_profiles", "personal_facts", "resume_variant_revisions"]:
        op.add_column(table, sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.add_column("resume_variant_revisions", sa.Column("library_number", sa.Integer()))
    op.add_column("resume_variant_revisions", sa.Column("display_name", sa.String(200)))
    op.add_column(
        "resume_variant_revisions",
        sa.Column("metadata_revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.execute("""WITH numbered AS (SELECT id, row_number() OVER (ORDER BY created_at, id) AS n
        FROM resume_variant_revisions)
        UPDATE resume_variant_revisions r SET library_number=n.n, display_name='简历 · ' || n.n
        FROM numbered n WHERE r.id=n.id""")
    op.execute("""WITH named AS (
        SELECT r.id, c.name AS company, j.title,
               row_number() OVER (PARTITION BY j.job_id ORDER BY r.created_at, r.id) AS n
        FROM resume_variant_revisions r JOIN job_revisions j ON j.id=r.job_revision_id
        JOIN job_postings p ON p.id=j.job_id JOIN companies c ON c.id=p.company_id)
        UPDATE resume_variant_revisions r
        SET display_name=left(n.company || ' · ' || n.title || ' · 优化版 ' || n.n, 200)
        FROM named n WHERE n.id=r.id""")
    op.create_unique_constraint(
        "uq_resume_variant_revisions_library_number", "resume_variant_revisions", ["library_number"]
    )
    op.execute("""CREATE OR REPLACE FUNCTION prevent_resume_revision_update() RETURNS trigger AS $$
        BEGIN
        IF (to_jsonb(NEW) - ARRAY['display_name','metadata_revision','archived_at'])
            IS DISTINCT FROM
           (to_jsonb(OLD) - ARRAY['display_name','metadata_revision','archived_at']) THEN
            RAISE EXCEPTION 'resume_revision_immutable';
        END IF;
        RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER resume_revision_immutable BEFORE UPDATE ON resume_variant_revisions
        FOR EACH ROW EXECUTE FUNCTION prevent_resume_revision_update()""")
    op.create_table(
        "profile_workspaces",
        sa.Column("key", sa.String(30), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "current_profile_id",
            sa.Uuid(),
            sa.ForeignKey("personal_profiles.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "base_profile_id", sa.Uuid(), sa.ForeignKey("personal_profiles.id", ondelete="RESTRICT")
        ),
        sa.Column("data", pg.JSONB(), nullable=False),
        sa.Column("section_revisions", pg.JSONB(), nullable=False),
    )
    op.create_table(
        "profile_photos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
    )
    op.create_table(
        "resume_workspaces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "profile_id", sa.Uuid(), sa.ForeignKey("personal_profiles.id", ondelete="RESTRICT")
        ),
        sa.Column("source", pg.JSONB(), nullable=False),
        sa.Column("document", pg.JSONB(), nullable=False),
        sa.Column(
            "accepted_revision_id",
            sa.Uuid(),
            sa.ForeignKey("resume_variant_revisions.id", ondelete="RESTRICT"),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    op.execute("""CREATE OR REPLACE FUNCTION prevent_resume_revision_update() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'resume_revision_immutable'; END; $$ LANGUAGE plpgsql""")
    for table in ["resume_workspaces", "profile_photos", "profile_workspaces"]:
        op.drop_table(table)
    op.drop_constraint(
        "uq_resume_variant_revisions_library_number", "resume_variant_revisions", type_="unique"
    )
    for name in ["metadata_revision", "display_name", "library_number"]:
        op.drop_column("resume_variant_revisions", name)
    for table in ["resume_variant_revisions", "personal_facts", "personal_profiles"]:
        op.drop_column(table, "archived_at")
