from enum import StrEnum


class DomainError(Exception):
    def __init__(self, code: str, status_code: int = 409) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


class FactStatus(StrEnum):
    PROPOSED = "proposed"
    VERIFIED = "verified"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class ApplicationStatus(StrEnum):
    TRACKING = "tracking"
    PREPARING = "preparing"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    CLOSED = "closed"


class RunStatus(StrEnum):
    COMPLETED = "completed"
    WAITING_INPUT = "waiting_input"
    WAITING_DECISION = "waiting_decision"
    CANCELLED = "cancelled"
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    NEEDS_INPUT = "needs_input"
    DECISION_REQUIRED = "decision_required"


class CallStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ObservationStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    ERROR = "error"


def verify_fact(status: FactStatus, *, explicit_user_action: bool) -> FactStatus:
    if not explicit_user_action:
        raise DomainError("explicit_verification_required", 403)
    if status != FactStatus.PROPOSED:
        raise DomainError("invalid_fact_transition")
    return FactStatus.VERIFIED


def transition_application(
    current: ApplicationStatus,
    target: ApplicationStatus,
    *,
    correction: bool = False,
    reason: str | None = None,
    explicit_user_action: bool = False,
) -> None:
    if not explicit_user_action:
        raise DomainError("explicit_status_action_required", 403)
    if correction and (not reason or not reason.strip()):
        raise DomainError("correction_reason_required", 422)


def application_status(value: ApplicationStatus) -> ApplicationStatus:
    """Canonical Product status; historical event values are never rewritten."""
    return {
        ApplicationStatus.PREPARING: ApplicationStatus.TRACKING,
        ApplicationStatus.WITHDRAWN: ApplicationStatus.CLOSED,
    }.get(value, value)
