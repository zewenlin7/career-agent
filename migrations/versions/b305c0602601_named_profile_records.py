"""Named independent profiles and observable fact modification times."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "b305c0602601"
down_revision = "b205c0502601"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("resume_workspaces", sa.Column("source_resume_revision_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_resume_workspaces_source_resume",
        "resume_workspaces",
        "resume_variant_revisions",
        ["source_resume_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column("resume_workspaces", sa.Column("request_id", sa.Uuid()))
    op.add_column("resume_workspaces", sa.Column("number", sa.Integer()))
    op.add_column("resume_workspaces", sa.Column("parent_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_resume_workspaces_parent_id_resume_workspaces",
        "resume_workspaces",
        "resume_workspaces",
        ["parent_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_resume_workspaces_request_id", "resume_workspaces", ["request_id"]
    )
    op.create_unique_constraint("uq_resume_workspaces_number", "resume_workspaces", ["number"])
    op.execute("""WITH numbered AS (SELECT id, row_number() OVER (ORDER BY created_at,id) +
        (SELECT coalesce(max(library_number),0) FROM resume_variant_revisions) AS n
        FROM resume_workspaces) UPDATE resume_workspaces r SET number=n.n,
        name=CASE WHEN r.name='简历草稿' THEN '简历 ' || n.n ELSE r.name END
        FROM numbered n WHERE r.id=n.id""")
    op.execute(
        "UPDATE resume_variant_revisions "
        "SET display_name=replace(display_name, '简历 · ', '简历 ') "
        "WHERE display_name LIKE '简历 · %'"
    )
    op.create_table(
        "profile_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("data", pg.JSONB(), nullable=False),
        sa.Column("section_revisions", pg.JSONB(), nullable=False),
        sa.Column(
            "profile_id", sa.Uuid(), sa.ForeignKey("personal_profiles.id", ondelete="RESTRICT")
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "profile_record_snapshots",
        sa.Column(
            "record_id",
            sa.Uuid(),
            sa.ForeignKey("profile_records.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("personal_profiles.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    # Each historical snapshot remains independently discoverable; never guess a lineage.
    op.execute("""INSERT INTO profile_records
        (id, created_at, number, name, revision, data, section_revisions, profile_id, archived_at)
        SELECT id, created_at, revision, '个人资料 ' || revision, 1, data,
        '{"personal": 1,"education": 1,"experiences": 1,"projects": 1,
        "skills": 1,"preferences": 1}'::jsonb,
        id, archived_at FROM personal_profiles""")
    op.execute("INSERT INTO profile_record_snapshots SELECT id, profile_id FROM profile_records")
    # Historical modification times are unknown, not fabricated from creation time.
    op.add_column("personal_facts", sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.execute("""CREATE FUNCTION fact_modification_time() RETURNS trigger AS $$
        BEGIN NEW.updated_at = clock_timestamp(); RETURN NEW; END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER fact_modification_time BEFORE INSERT OR UPDATE ON personal_facts
        FOR EACH ROW EXECUTE FUNCTION fact_modification_time()""")


def downgrade():
    op.drop_constraint(
        "fk_resume_workspaces_source_resume",
        "resume_workspaces",
        type_="foreignkey",
    )
    op.drop_column("resume_workspaces", "source_resume_revision_id")
    op.drop_constraint(
        "fk_resume_workspaces_parent_id_resume_workspaces", "resume_workspaces", type_="foreignkey"
    )
    op.drop_constraint("uq_resume_workspaces_request_id", "resume_workspaces", type_="unique")
    op.drop_constraint("uq_resume_workspaces_number", "resume_workspaces", type_="unique")
    for name in ["parent_id", "number", "request_id"]:
        op.drop_column("resume_workspaces", name)
    op.execute("DROP TRIGGER fact_modification_time ON personal_facts")
    op.execute("DROP FUNCTION fact_modification_time()")
    op.drop_column("personal_facts", "updated_at")
    op.drop_table("profile_record_snapshots")
    op.drop_table("profile_records")
