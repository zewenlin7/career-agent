"""Display numbers belong to active roots, not immutable revisions."""

from alembic import op

revision = "b705c1002601"
down_revision = "b605c0902601"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("uq_resume_workspaces_number", "resume_workspaces", type_="unique")
    op.drop_constraint(
        "uq_resume_variant_revisions_library_number", "resume_variant_revisions", type_="unique"
    )


def downgrade():
    # Fail rather than renumber historical data if display numbers have been reused.
    op.create_unique_constraint("uq_resume_workspaces_number", "resume_workspaces", ["number"])
    op.create_unique_constraint(
        "uq_resume_variant_revisions_library_number", "resume_variant_revisions", ["library_number"]
    )
