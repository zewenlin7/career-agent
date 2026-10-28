"""Stable display anchors derived server-side and frozen with interview sources."""

from uuid import UUID

from career_agent.domain.schemas import InterviewEntry


def numbered(
    entries: list[InterviewEntry], previous: list[InterviewEntry] | None = None
) -> list[InterviewEntry]:
    old = {e.entry_id: e for e in (entries if previous is None else previous)}
    result = [e.model_copy(deep=True) for e in entries]
    # Retain assigned anchors on text edits/reordering, not on a changed parent relationship.
    for e in result:
        prior = old.get(e.entry_id)
        if prior and (prior.kind, prior.primary_entry_id) == (e.kind, e.primary_entry_id):
            e.main_question_number, e.followup_index = (
                prior.main_question_number,
                prior.followup_index,
            )
        else:
            e.main_question_number = e.followup_index = None
    maximum = max((e.main_question_number or 0 for e in [*old.values(), *result]), default=0)
    for e in sorted(result, key=lambda x: x.order):
        if e.kind == "primary" and e.main_question_number is None:
            maximum += 1
            e.main_question_number = maximum
    primaries = {e.entry_id: e for e in result if e.kind == "primary"}
    next_follow: dict[UUID, int] = {}
    for e in [*old.values(), *result]:
        if e.primary_entry_id and e.followup_index:
            next_follow[e.primary_entry_id] = max(
                next_follow.get(e.primary_entry_id, 0), e.followup_index
            )
    for e in sorted(result, key=lambda x: x.order):
        if e.kind == "follow_up" and e.primary_entry_id in primaries:
            assert e.primary_entry_id is not None
            e.main_question_number = primaries[e.primary_entry_id].main_question_number
            if e.followup_index is None:
                next_follow[e.primary_entry_id] = next_follow.get(e.primary_entry_id, 0) + 1
                e.followup_index = next_follow[e.primary_entry_id]
    return result


def anchor(entry: InterviewEntry) -> str:
    return (
        f"{entry.main_question_number}.{entry.followup_index}"
        if entry.kind == "follow_up"
        else str(entry.main_question_number)
    )
