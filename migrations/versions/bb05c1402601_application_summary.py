"""Explicit note ownership and append-only presentation edits."""

import sqlalchemy as sa
from alembic import op

revision = "bb05c1402601"
down_revision = "ba05c1302601"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mock_interview_sessions", sa.Column("display_number", sa.Integer(), nullable=True)
    )
    op.execute(
        """WITH numbered AS (SELECT id, row_number() OVER (
        PARTITION BY context->>'job_id' ORDER BY created_at, id) AS n
        FROM mock_interview_sessions)
        UPDATE mock_interview_sessions m SET display_number=n.n FROM numbered n WHERE m.id=n.id"""
    )
    op.add_column("application_events", sa.Column("source", sa.String(30), nullable=True))
    op.add_column("application_events", sa.Column("request_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(
        "uq_application_events_request_id", "application_events", ["request_id"]
    )
    op.create_table(
        "application_entry_edits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "event_id",
            sa.Uuid(),
            sa.ForeignKey("application_events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("removed", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("event_id", "revision"),
        sa.UniqueConstraint("request_id"),
    )
    # Legacy note ownership cannot be inferred from text or absence of a submission.
    op.execute("""CREATE FUNCTION protect_application_entry_edit() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'immutable_application_entry_edit'; END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER immutable_application_entry_edit
    BEFORE UPDATE ON application_entry_edits
    FOR EACH ROW EXECUTE FUNCTION protect_application_entry_edit()""")


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS(SELECT 1 FROM application_entry_edits)"))
        .scalar()
    ):
        raise RuntimeError("application_entry_history_requires_retention")
    op.drop_column("mock_interview_sessions", "display_number")
    op.drop_table("application_entry_edits")
    op.execute("DROP FUNCTION protect_application_entry_edit()")
    op.drop_constraint("uq_application_events_request_id", "application_events", type_="unique")
    op.drop_column("application_events", "request_id")
    op.drop_column("application_events", "source")
