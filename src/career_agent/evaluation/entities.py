"""Evaluation-private persistence; never a body-bearing operational trace table."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from career_agent.evaluation.contracts import (
    Annotation,
    CandidateConfig,
    CapturePayload,
    EvalCase,
    EvalRunRequest,
    EvalSuite,
    Feedback,
    JudgeOutput,
    JudgeSpec,
    OperationSnapshot,
    SamplingDecision,
    TrialResult,
)
from career_agent.infrastructure.db import Base, ValidatedJSON
from career_agent.infrastructure.entities import Row


class EvalCaseRow(Row, Base):
    __tablename__ = "eval_cases"
    __table_args__ = (UniqueConstraint("case_key", "version"),)
    case_key: Mapped[str] = mapped_column(String(128))
    version: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(EvalCase))


class EvalSuiteRow(Row, Base):
    __tablename__ = "eval_suites"
    __table_args__ = (UniqueConstraint("suite_key", "version"),)
    suite_key: Mapped[str] = mapped_column(String(128))
    version: Mapped[int]
    data: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(EvalSuite))


class EvalRunRow(Row, Base):
    __tablename__ = "eval_runs"
    suite_id: Mapped[UUID] = mapped_column(ForeignKey("eval_suites.id", ondelete="RESTRICT"))
    request: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(EvalRunRequest))
    candidate: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(CandidateConfig))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason_code: Mapped[str | None] = mapped_column(String(128))


class EvalTrialRow(Row, Base):
    __tablename__ = "eval_trials"
    __table_args__ = (UniqueConstraint("run_id", "case_id", "trial_index"),)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="RESTRICT"), index=True
    )
    case_id: Mapped[UUID] = mapped_column(ForeignKey("eval_cases.id", ondelete="RESTRICT"))
    trial_index: Mapped[int]
    status: Mapped[str] = mapped_column(String(30), default="pending")
    result: Mapped[dict[str, Any] | None] = mapped_column(ValidatedJSON(TrialResult))


class InvocationRow(Row, Base):
    __tablename__ = "operation_invocations"
    trial_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("eval_trials.id", ondelete="RESTRICT"), index=True
    )
    model_call_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("model_calls.id", ondelete="RESTRICT"), unique=True
    )
    data: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(OperationSnapshot))


class SamplingRow(Row, Base):
    __tablename__ = "judge_sampling_decisions"
    decision_key: Mapped[str] = mapped_column(String(64), unique=True)
    subject_id: Mapped[UUID] = mapped_column(index=True)
    data: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(SamplingDecision))


class JudgeRow(Row, Base):
    __tablename__ = "judge_evaluations"
    sampling_id: Mapped[UUID] = mapped_column(
        ForeignKey("judge_sampling_decisions.id", ondelete="RESTRICT")
    )
    spec: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(JudgeSpec))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    model_call_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("model_calls.id", ondelete="RESTRICT")
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(ValidatedJSON(JudgeOutput))
    severity: Mapped[str | None] = mapped_column(String(30))
    reason_code: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FeedbackRow(Row, Base):
    __tablename__ = "user_feedback"
    subject_id: Mapped[UUID] = mapped_column(index=True)
    data: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(Feedback))


class AnnotationRow(Row, Base):
    __tablename__ = "human_annotations"
    subject_id: Mapped[UUID] = mapped_column(index=True)
    data: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(Annotation))


class AnnotationQueueRow(Row, Base):
    __tablename__ = "human_annotation_queue"
    subject_id: Mapped[UUID] = mapped_column(index=True)
    population: Mapped[str] = mapped_column(String(20))
    rubric_version: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(30), default="pending")


class CaptureRow(Row, Base):
    __tablename__ = "bad_case_captures"
    subject_id: Mapped[UUID] = mapped_column(unique=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(ValidatedJSON(CapturePayload))
    status: Mapped[str] = mapped_column(String(30), default="captured")


class CaptureEventRow(Row, Base):
    __tablename__ = "bad_case_capture_events"
    capture_id: Mapped[UUID] = mapped_column(
        ForeignKey("bad_case_captures.id", ondelete="RESTRICT"), index=True
    )
    kind: Mapped[str] = mapped_column(String(128))
    reference_id: Mapped[UUID | None]
    reason_code: Mapped[str | None] = mapped_column(String(128))


class ComparisonRow(Row, Base):
    __tablename__ = "eval_comparisons"
    baseline_id: Mapped[UUID] = mapped_column(ForeignKey("eval_runs.id", ondelete="RESTRICT"))
    candidate_id: Mapped[UUID] = mapped_column(ForeignKey("eval_runs.id", ondelete="RESTRICT"))
    policy_version: Mapped[str] = mapped_column(String(128))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
