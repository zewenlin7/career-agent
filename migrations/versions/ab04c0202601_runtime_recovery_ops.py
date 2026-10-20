"""Durable control journal, recovery and operational facts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "ab04c0202601"
down_revision = "ca63e5f34564"
branch_labels = None
depends_on = None


def common():
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    ]


def upgrade():
    op.create_table(
        "controller_states",
        *common(),
        sa.Column("scope", sa.String(128), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("scope"),
        sa.CheckConstraint("revision >= 0", name="revision"),
    )
    op.create_table(
        "attempt_journals",
        *common(),
        sa.Column("scope", sa.String(128), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("attempt_id"),
        sa.CheckConstraint(
            "status IN ('reserved','dispatch_intent','unknown','settled',"
            "'not_dispatched','business_committed')",
            name="status",
        ),
    )
    op.create_index("ix_attempt_journals_scope", "attempt_journals", ["scope"])
    op.create_index("ix_attempt_journals_operation_id", "attempt_journals", ["operation_id"])
    op.create_table(
        "control_events",
        *common(),
        sa.Column("scope", sa.String(128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("scope", "sequence", name="uq_control_event_sequence"),
        sa.UniqueConstraint("scope", "request_id", name="uq_control_event_request"),
    )
    op.create_table(
        "recovery_incidents",
        *common(),
        sa.Column("scope", sa.String(128), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(128), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("resolution", sa.String(128)),
        sa.UniqueConstraint("attempt_id"),
    )
    op.create_index("ix_recovery_incidents_scope", "recovery_incidents", ["scope"])
    op.execute("""CREATE FUNCTION reject_control_event_mutation() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'immutable_control_event'; END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER immutable_control_event BEFORE UPDATE OR DELETE ON control_events
    FOR EACH ROW EXECUTE FUNCTION reject_control_event_mutation()""")

    op.execute("""CREATE FUNCTION protect_attempt_identity() RETURNS trigger AS $$
    BEGIN
      IF NEW.scope IS DISTINCT FROM OLD.scope OR NEW.attempt_id IS DISTINCT FROM OLD.attempt_id
         OR NEW.operation_id IS DISTINCT FROM OLD.operation_id
         OR NEW.data->'selection' IS DISTINCT FROM OLD.data->'selection'
         OR NEW.data->'financial_reservation' IS DISTINCT FROM OLD.data->'financial_reservation'
         OR NEW.data->'budget_owner_refs' IS DISTINCT FROM OLD.data->'budget_owner_refs' THEN
        RAISE EXCEPTION 'immutable_attempt_identity';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER immutable_attempt_identity BEFORE UPDATE ON attempt_journals
    FOR EACH ROW EXECUTE FUNCTION protect_attempt_identity()""")


def downgrade():
    op.drop_table("recovery_incidents")
    op.drop_table("control_events")
    op.execute("DROP FUNCTION reject_control_event_mutation()")
    op.drop_table("attempt_journals")
    op.execute("DROP FUNCTION protect_attempt_identity()")
    op.drop_table("controller_states")
