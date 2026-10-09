"""Reference and hard-token checks, not a semantic truth/exaggeration judge."""

import re
from dataclasses import dataclass
from uuid import UUID

from career_agent.domain.rules import FactStatus
from career_agent.resume.schemas import Finding, InputSnapshot, ResumeDocument


@dataclass(frozen=True)
class FactEvidence:
    id: UUID
    revision: int
    status: FactStatus
    statement: str


def numbers(value: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)*(?:%)?", value))


def validate_grounding(
    document: ResumeDocument,
    snapshot: InputSnapshot,
    profile_fact_ids: set[UUID],
    facts: dict[UUID, FactEvidence],
    requirements: set[UUID],
) -> list[Finding]:
    findings: list[Finding] = []
    snapshots = {f.fact_id: f.revision for f in snapshot.facts}
    for section in document.sections:
        for item in section.items:
            supported = []
            for fact_id in item.fact_refs:
                fact = facts.get(fact_id)
                if fact is None or fact.status != FactStatus.VERIFIED:
                    findings.append(
                        Finding(
                            code="missing_verified_fact", item_id=item.item_id, reference_id=fact_id
                        )
                    )
                elif fact_id not in profile_fact_ids or snapshots.get(fact_id) != fact.revision:
                    findings.append(
                        Finding(
                            code="snapshot_mismatch", item_id=item.item_id, reference_id=fact_id
                        )
                    )
                else:
                    supported.append(fact.statement)
            for requirement in item.requirement_refs:
                if requirement not in requirements:
                    findings.append(
                        Finding(
                            code="invalid_requirement_reference",
                            item_id=item.item_id,
                            reference_id=requirement,
                        )
                    )
            evidence_numbers = numbers(" ".join(supported))
            for text in [item.text, item.short_text]:
                if text and not numbers(text) <= evidence_numbers:
                    findings.append(Finding(code="hard_field_mismatch", item_id=item.item_id))
            for claim in item.hard_claims:
                fact = facts.get(claim.fact_ref)
                if (
                    claim.fact_ref not in item.fact_refs
                    or fact is None
                    or claim.value.casefold() not in fact.statement.casefold()
                    or claim.value.casefold() not in item.text.casefold()
                ):
                    findings.append(Finding(code="hard_field_mismatch", item_id=item.item_id))
    return findings
