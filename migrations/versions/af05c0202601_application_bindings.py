"""Application defaults with exact bindings; legacy personal context is never guessed."""

import sqlalchemy as sa
from alembic import op

revision = "af05c0202601"
down_revision = "ae05c0102601"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "application_bindings",
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "profile_id", sa.Uuid(), sa.ForeignKey("personal_profiles.id", ondelete="RESTRICT")
        ),
        sa.Column(
            "resume_revision_id",
            sa.Uuid(),
            sa.ForeignKey("resume_variant_revisions.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "job_revision_id",
            sa.Uuid(),
            sa.ForeignKey("job_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("""INSERT INTO application_bindings
        (application_id, revision, profile_id, resume_revision_id, job_revision_id, updated_at)
        SELECT a.id, 1, NULL, NULL, j.id, CURRENT_TIMESTAMP
        FROM applications a JOIN job_postings p ON p.id = a.job_id
        JOIN job_revisions j ON j.job_id = p.id AND j.revision = p.current_revision""")


def downgrade():
    op.drop_table("application_bindings")
