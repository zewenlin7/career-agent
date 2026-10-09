import pytest
from pydantic import ValidationError

from career_agent.domain.rules import (
    ApplicationStatus as A,
)
from career_agent.domain.rules import (
    DomainError,
    reject_fact,
    replace_fact,
    transition_application,
    verify_fact,
)
from career_agent.domain.rules import (
    FactStatus as F,
)
from career_agent.domain.schemas import ApplicationChange, FactCreate, ProfileWrite
from career_agent.runtime.contracts import Usage, VersionMetadata


def test_fact_lifecycle():
    assert verify_fact(F.PROPOSED, explicit_user_action=True) == F.VERIFIED
    assert replace_fact(F.VERIFIED) == F.SUPERSEDED
    assert reject_fact(F.PROPOSED) == F.REJECTED
    assert reject_fact(F.VERIFIED) == F.REJECTED


@pytest.mark.parametrize("status", [F.VERIFIED, F.SUPERSEDED, F.REJECTED])
def test_verify_invalid_state(status):
    with pytest.raises(DomainError):
        verify_fact(status, explicit_user_action=True)


def test_import_cannot_verify():
    with pytest.raises(DomainError, match="explicit_verification_required"):
        verify_fact(F.PROPOSED, explicit_user_action=False)
    with pytest.raises(ValidationError):
        FactCreate(statement="Synthetic", category="project", status="verified")


@pytest.mark.parametrize("status", [F.PROPOSED, F.SUPERSEDED, F.REJECTED])
def test_invalid_replacement(status):
    with pytest.raises(DomainError):
        replace_fact(status)


@pytest.mark.parametrize(
    "start,end",
    [
        (A.TRACKING, A.PREPARING),
        (A.TRACKING, A.APPLIED),
        (A.PREPARING, A.APPLIED),
        (A.APPLIED, A.INTERVIEWING),
        (A.INTERVIEWING, A.OFFER),
        (A.APPLIED, A.REJECTED),
        (A.OFFER, A.CLOSED),
        (A.TRACKING, A.WITHDRAWN),
    ],
)
def test_valid_application_transitions(start, end):
    transition_application(start, end, explicit_user_action=True)


@pytest.mark.parametrize(
    "start,end",
    [(A.TRACKING, A.OFFER), (A.REJECTED, A.APPLIED), (A.APPLIED, A.TRACKING), (A.CLOSED, A.CLOSED)],
)
def test_invalid_application_transitions(start, end):
    with pytest.raises(DomainError):
        transition_application(start, end, explicit_user_action=True)


def test_explicit_application_and_correction():
    with pytest.raises(DomainError):
        transition_application(A.TRACKING, A.APPLIED)
    with pytest.raises(DomainError):
        transition_application(A.REJECTED, A.APPLIED, correction=True, explicit_user_action=True)
    transition_application(
        A.REJECTED,
        A.APPLIED,
        correction=True,
        reason="Synthetic correction",
        explicit_user_action=True,
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_revision": 1, "status": "invented"},
        {"expected_revision": 1, "status": "applied", "correction": True},
        {"expected_revision": -1, "status": "applied"},
    ],
)
def test_invalid_application_payload(payload):
    with pytest.raises(ValidationError):
        ApplicationChange.model_validate(payload)


def test_schema_and_version_contract():
    with pytest.raises(ValidationError):
        ProfileWrite(expected_revision=0, data={"display_name": " "})
    assert VersionMetadata().prompt_version is None
    with pytest.raises(ValidationError):
        VersionMetadata(prompt_version="/private/example/prompt.txt")
    with pytest.raises(ValidationError):
        Usage(input_tokens=-1)
    assert Usage().estimated_cost is None  # unknown is not zero
