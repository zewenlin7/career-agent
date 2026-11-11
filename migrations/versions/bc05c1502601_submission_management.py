"""Submission presentation edits retain immutable materials and audit history."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "bc05c1502601"
down_revision = "bb05c1402601"
branch_labels = None
depends_on = None


def upgrade():
    # Historical successful tailoring already has an exact revision identity.
    op.execute("""UPDATE resume_variants SET library_visible=true WHERE id IN (
        SELECT r.resume_variant_id FROM resume_variant_revisions r
        JOIN preparation_artifacts a ON a.data->'output'->>'resume_revision_id'=r.id::text
        WHERE a.data->>'kind'='target' AND a.data->'output'->>'target'='resume_tailoring'
    )""")
    op.add_column("material_submissions", sa.Column("display_number", sa.Integer(), nullable=True))
    op.execute("""WITH numbered AS (
        SELECT id, row_number() OVER (PARTITION BY application_id ORDER BY created_at, id) n
        FROM material_submissions)
        UPDATE material_submissions s SET display_number=n.n FROM numbered n WHERE s.id=n.id""")
    op.alter_column("material_submissions", "display_number", nullable=False)
    op.add_column(
        "material_submissions",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("material_submissions", sa.Column("note_override", sa.Text(), nullable=True))
    op.add_column(
        "material_submissions", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "material_submissions",
        sa.Column("edits", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.alter_column("material_submissions", "revision", server_default=None)
    op.alter_column("material_submissions", "edits", server_default=None)


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS(SELECT 1 FROM material_submissions WHERE revision > 1)"))
        .scalar()
    ):
        raise RuntimeError("submission_history_requires_retention")
    for name in ["edits", "deleted_at", "note_override", "revision", "display_number"]:
        op.drop_column("material_submissions", name)
