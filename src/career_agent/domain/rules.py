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
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    NEEDS_INPUT = "needs_input"


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


def replace_fact(status: FactStatus) -> FactStatus:
    if status != FactStatus.VERIFIED:
        raise DomainError("invalid_fact_transition")
    return FactStatus.SUPERSEDED


def reject_fact(status: FactStatus) -> FactStatus:
    if status not in {FactStatus.PROPOSED, FactStatus.VERIFIED}:
        raise DomainError("invalid_fact_transition")
    return FactStatus.REJECTED


def transition_application(
    current: ApplicationStatus,
    target: ApplicationStatus,
    *,
    correction: bool = False,
    reason: str | None = None,
    explicit_user_action: bool = False,
) -> None:
    if current == target:
        raise DomainError("unchanged_application_status")
    if not explicit_user_action:
        raise DomainError("explicit_status_action_required", 403)
    if correction:
        if not reason or not reason.strip():
            raise DomainError("correction_reason_required", 422)
        return
    allowed = {
        ApplicationStatus.TRACKING: {
            ApplicationStatus.PREPARING,
            ApplicationStatus.APPLIED,
            ApplicationStatus.WITHDRAWN,
            ApplicationStatus.CLOSED,
        },
        ApplicationStatus.PREPARING: {
            ApplicationStatus.APPLIED,
            ApplicationStatus.WITHDRAWN,
            ApplicationStatus.CLOSED,
        },
        ApplicationStatus.APPLIED: {
            ApplicationStatus.INTERVIEWING,
            ApplicationStatus.OFFER,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
            ApplicationStatus.CLOSED,
        },
        ApplicationStatus.INTERVIEWING: {
            ApplicationStatus.OFFER,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
            ApplicationStatus.CLOSED,
        },
        ApplicationStatus.OFFER: {ApplicationStatus.WITHDRAWN, ApplicationStatus.CLOSED},
    }
    if target not in allowed.get(current, set()):
        raise DomainError("invalid_application_transition")
