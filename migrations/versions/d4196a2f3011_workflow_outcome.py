"""Canonical preparation outcome; preserve legacy run statuses."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4196a2f3011"
down_revision = "c38190f12a01"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("agent_runs", "status", existing_type=sa.String(11), type_=sa.String(17))
    op.add_column("agent_runs", sa.Column("outcome", postgresql.JSONB(), nullable=True))
    op.drop_constraint(op.f("ck_agent_runs_runstatus"), "agent_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_runs_runstatus"),
        "agent_runs",
        "status IN ('pending','running','succeeded','partial','failed',"
        "'interrupted','needs_input','decision_required')",
    )


def downgrade():
    op.execute("UPDATE agent_runs SET status='needs_input' WHERE status='decision_required'")
    op.drop_constraint(op.f("ck_agent_runs_runstatus"), "agent_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_runs_runstatus"),
        "agent_runs",
        "status IN ('pending','running','succeeded','partial','failed',"
        "'interrupted','needs_input')",
    )
    op.alter_column("agent_runs", "status", existing_type=sa.String(17), type_=sa.String(11))
    op.drop_column("agent_runs", "outcome")
