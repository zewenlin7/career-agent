"""Interview operation/accepted-call provenance; historical unknown associations stay null."""

import sqlalchemy as sa
from alembic import op

revision = "b952d4e23453"
down_revision = "a841c3d12342"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("model_calls", sa.Column("logical_operation_id", sa.Uuid(), nullable=True))
    op.create_index("ix_model_calls_logical_operation_id", "model_calls", ["logical_operation_id"])
    op.create_unique_constraint(
        "uq_model_calls_logical_operation_id", "model_calls", ["logical_operation_id", "attempts"]
    )
    op.add_column(
        "mock_interview_sessions", sa.Column("generation_operation_id", sa.Uuid(), nullable=True)
    )
    for table in ("mock_interview_turns", "debrief_artifacts"):
        op.add_column(table, sa.Column("logical_operation_id", sa.Uuid(), nullable=True))
        op.add_column(table, sa.Column("accepted_model_call_id", sa.Uuid(), nullable=True))
        op.create_unique_constraint(
            f"uq_{table}_logical_operation_id", table, ["logical_operation_id"]
        )
        op.create_unique_constraint(
            f"uq_{table}_accepted_model_call_id", table, ["accepted_model_call_id"]
        )
        op.create_foreign_key(
            f"fk_{table}_accepted_model_call_id_model_calls",
            table,
            "model_calls",
            ["accepted_model_call_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade():
    for table in ("debrief_artifacts", "mock_interview_turns"):
        op.drop_constraint(
            f"fk_{table}_accepted_model_call_id_model_calls", table, type_="foreignkey"
        )
        op.drop_constraint(f"uq_{table}_accepted_model_call_id", table, type_="unique")
        op.drop_constraint(f"uq_{table}_logical_operation_id", table, type_="unique")
        op.drop_column(table, "accepted_model_call_id")
        op.drop_column(table, "logical_operation_id")
    op.drop_column("mock_interview_sessions", "generation_operation_id")
    op.drop_constraint("uq_model_calls_logical_operation_id", "model_calls", type_="unique")
    op.drop_index("ix_model_calls_logical_operation_id", table_name="model_calls")
    op.drop_column("model_calls", "logical_operation_id")
