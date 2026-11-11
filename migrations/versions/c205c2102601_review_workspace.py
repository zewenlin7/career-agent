"""Review visibility, execution receipts and honest note modification timestamps."""

import sqlalchemy as sa
from alembic import op

revision = "c205c2102601"
down_revision = "c105c2002601"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, type_ in [
        ("request_id", sa.Uuid()),
        ("request_hash", sa.String(64)),
        ("updated_at", sa.DateTime(timezone=True)),
    ]:
        op.add_column("knowledge_notes", sa.Column(name, type_, nullable=True))
    op.create_unique_constraint("uq_knowledge_notes_request_id", "knowledge_notes", ["request_id"])
    op.add_column("debrief_runs", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column(
        "debrief_runs",
        sa.Column("execution_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.drop_constraint("uq_debrief_runs_request_fingerprint", "debrief_runs", type_="unique")
    op.create_index(
        "uq_debrief_runs_request_fingerprint",
        "debrief_runs",
        ["request_fingerprint"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "debrief_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "debrief_id",
            sa.Uuid(),
            sa.ForeignKey("debrief_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("execution_revision", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM debrief_requests) "
            "OR EXISTS(SELECT 1 FROM debrief_runs WHERE deleted_at IS NOT NULL "
            "OR execution_revision > 0) OR EXISTS(SELECT 1 FROM knowledge_notes "
            "WHERE request_id IS NOT NULL OR updated_at IS NOT NULL)"
        )
    ):
        raise RuntimeError("review_workspace_history_requires_retention")
    op.drop_table("debrief_requests")
    op.drop_index("uq_debrief_runs_request_fingerprint", "debrief_runs")
    op.create_unique_constraint(
        "uq_debrief_runs_request_fingerprint", "debrief_runs", ["request_fingerprint"]
    )
    op.drop_column("debrief_runs", "execution_revision")
    op.drop_column("debrief_runs", "deleted_at")
    op.drop_constraint("uq_knowledge_notes_request_id", "knowledge_notes", type_="unique")
    for name in ["updated_at", "request_hash", "request_id"]:
        op.drop_column("knowledge_notes", name)
