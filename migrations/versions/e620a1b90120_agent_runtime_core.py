"""Bounded agent state, append-only plans/checkpoints and action observations."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "e620a1b90120"
down_revision = "d4196a2f3011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_runs", sa.Column("parent_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_agent_runs_parent_run_id_agent_runs"),
        "agent_runs",
        "agent_runs",
        ["parent_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "agent_runs",
        sa.Column("run_kind", sa.String(20), server_default="workflow", nullable=False),
    )
    op.drop_constraint(op.f("ck_agent_runs_runstatus"), "agent_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_runs_runstatus"),
        "agent_runs",
        "status IN ('pending','running','succeeded','partial','failed','interrupted','needs_input',"
        "'decision_required','completed','waiting_input','waiting_decision','cancelled')",
    )
    for name, typ in [
        ("action_id", sa.Uuid()),
        ("plan_revision", sa.Integer()),
        ("transition", pg.JSONB()),
    ]:
        op.add_column("agent_steps", sa.Column(name, typ, nullable=True))
    op.add_column("observations", sa.Column("action_step_id", sa.Uuid(), nullable=True))
    op.add_column("observations", sa.Column("action_data", pg.JSONB(), nullable=True))
    op.create_foreign_key(
        op.f("fk_observations_action_step_id_agent_steps"),
        "observations",
        "agent_steps",
        ["action_step_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(op.f("ck_observations_exactly_one_call"), "observations", type_="check")
    op.create_check_constraint(
        op.f("ck_observations_exactly_one_call"),
        "observations",
        "(CASE WHEN model_call_id IS NULL THEN 0 ELSE 1 END + CASE WHEN "
        "tool_call_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN action_step_id IS NULL THEN 0 ELSE 1 END) = 1",
    )
    op.create_check_constraint(
        op.f("ck_observations_action_data_pair"),
        "observations",
        "(action_step_id IS NULL) = (action_data IS NULL OR action_data = 'null'::jsonb)",
    )
    for table, payload, extra in [
        ("agent_goals", "data", []),
        ("agent_plans", "data", [sa.Column("revision", sa.Integer(), nullable=False)]),
        ("agent_checkpoints", "state", [sa.Column("revision", sa.Integer(), nullable=False)]),
    ]:
        constraints = (
            [sa.UniqueConstraint("run_id")]
            if not extra
            else [
                sa.UniqueConstraint("run_id", "revision"),
                sa.CheckConstraint("revision > 0", name=op.f("ck_" + table + "_positive_revision")),
            ]
        )
        op.create_table(
            table,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "run_id",
                sa.Uuid(),
                sa.ForeignKey("agent_runs.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            *extra,
            sa.Column(payload, pg.JSONB(), nullable=False),
            *constraints,
        )
    op.create_table(
        "agent_resume_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "run_id", sa.Uuid(), sa.ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("run_id", "request_id"),
    )


def downgrade():
    # Refuse loss of existing runtime goal history; empty/new databases can downgrade normally.
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM agent_goals)")):
        raise RuntimeError("runtime_history_requires_explicit_archive")
    for table in ["agent_resume_receipts", "agent_checkpoints", "agent_plans", "agent_goals"]:
        op.drop_table(table)
    op.drop_constraint(op.f("ck_observations_action_data_pair"), "observations", type_="check")
    op.drop_constraint(op.f("ck_observations_exactly_one_call"), "observations", type_="check")
    op.drop_column("observations", "action_step_id")
    op.drop_column("observations", "action_data")
    op.create_check_constraint(
        op.f("ck_observations_exactly_one_call"),
        "observations",
        "(model_call_id IS NOT NULL AND tool_call_id IS NULL) OR (model_call_id IS "
        "NULL AND tool_call_id IS NOT NULL)",
    )
    for name in ["transition", "plan_revision", "action_id"]:
        op.drop_column("agent_steps", name)
    op.drop_column("agent_runs", "parent_run_id")
    op.drop_column("agent_runs", "run_kind")
    op.drop_constraint(op.f("ck_agent_runs_runstatus"), "agent_runs", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_runs_runstatus"),
        "agent_runs",
        "status IN "
        "('pending','running','succeeded','partial','failed','interrupted','needs_input','decision_required')",
    )
