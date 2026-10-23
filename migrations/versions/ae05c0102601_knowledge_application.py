"""Optional direct Application ownership for Knowledge Notes; legacy links stay readable."""

import sqlalchemy as sa
from alembic import op

revision = "ae05c0102601"
down_revision = "ad04c0402601"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("knowledge_notes", sa.Column("application_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_knowledge_notes_application_id_applications",
        "knowledge_notes",
        "applications",
        ["application_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_knowledge_notes_application_id", "knowledge_notes", ["application_id"])


def downgrade():
    op.drop_index("ix_knowledge_notes_application_id", table_name="knowledge_notes")
    op.drop_constraint(
        "fk_knowledge_notes_application_id_applications", "knowledge_notes", type_="foreignkey"
    )
    op.drop_column("knowledge_notes", "application_id")
