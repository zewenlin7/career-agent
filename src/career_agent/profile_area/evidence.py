"""Resolve saved expression claims to authoritative user input, never verify AI wording."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import verify_user_fact
from career_agent.domain.rules import FactStatus
from career_agent.infrastructure import entities as e
from career_agent.profile_area.contracts import ResumeDraftData, WorkspaceData
from career_agent.profile_area.entities import ResumeWorkspace
from career_agent.resume.grounding import numbers


def user_sources(document: dict[str, Any], kind: str = "user") -> dict[str, Any]:
    return {
        i["item_id"]: {"kind": kind, "statement": i["text"]}
        for s in document["sections"]
        for i in s["items"]
    }


def edited_sources(source: ResumeWorkspace, document: dict[str, Any]) -> dict[str, Any]:
    original = {i["item_id"]: i for s in source.document["sections"] for i in s["items"]}
    return {
        i["item_id"]: (source.content_sources or {}).get(
            i["item_id"], {"kind": "legacy", "statement": ""}
        )
        if (i.get("text"), i.get("short_text"))
        == (
            original.get(i["item_id"], {}).get("text"),
            original.get(i["item_id"], {}).get("short_text"),
        )
        else {"kind": "user", "statement": i["text"]}
        for s in document["sections"]
        for i in s["items"]
    }


async def resolve_claims(session: AsyncSession, row: ResumeWorkspace) -> list[dict[str, Any]]:
    from career_agent.profile_area.service import draft_document

    sources = row.content_sources
    if sources is None:
        # Legacy records have no trustworthy author marker. Only exact original Profile
        # content can be recovered automatically; unknown edited/generated claims fail closed.
        originals = {
            i.text
            for s in draft_document(WorkspaceData.model_validate(row.source)).sections
            for i in s.items
        }
        sources = {
            i["item_id"]: {
                "kind": "profile",
                "statement": i["text"] if i["text"] in originals else "",
            }
            for s in row.document["sections"]
            for i in s["items"]
        }
    data = ResumeDraftData.model_validate(row.document)
    issues = []
    for section in data.sections:
        for item in section.items:
            evidence = sources.get(str(item.item_id), {})
            statement = evidence.get("statement", "")
            if (
                not statement
                or not numbers(item.text + (item.short_text or "")) <= numbers(statement)
                or any(
                    claim.fact_ref not in item.fact_refs
                    or claim.value.casefold() not in statement.casefold()
                    or claim.value.casefold() not in item.text.casefold()
                    for claim in item.hard_claims
                )
            ):
                issues.append(
                    {
                        "item_id": str(item.item_id),
                        "text": item.text,
                        "message": "这条描述缺少个人资料依据。",
                    }
                )
                continue
            fact = await session.scalar(
                select(e.PersonalFact)
                .where(
                    e.PersonalFact.statement == statement,
                    e.PersonalFact.archived_at.is_(None),
                    e.PersonalFact.status.in_([FactStatus.PROPOSED, FactStatus.VERIFIED]),
                )
                .order_by(e.PersonalFact.id)
                .limit(1)
            )
            if fact is None:
                fact = e.PersonalFact(
                    statement=statement,
                    category={
                        "projects": "project",
                        "experience": "experience",
                        "education": "education",
                        "skills": "skill",
                        "summary": "general",
                    }[section.name],
                    source_locator=f"resume-input:{row.id}:{item.item_id}",
                )
                session.add(fact)
                await session.flush()
            if fact.status != FactStatus.VERIFIED:
                # Statement is frozen user/Profile evidence, not model-generated expression.
                await verify_user_fact(session, fact.id)
            for claim in item.hard_claims:
                claim.fact_ref = fact.id
            item.fact_refs = [fact.id]
    if not issues:
        row.document = data.model_dump(mode="json")
    return issues


async def profile_evidence(session: AsyncSession, profile: e.PersonalProfile) -> set[UUID]:
    """Freeze literal user Profile claims for an explicitly requested Profile analysis."""
    from career_agent.profile_area.service import draft_document

    document = draft_document(WorkspaceData.model_validate(profile.data))
    ids = set()
    for section in document.sections:
        for item in section.items:
            fact = await session.scalar(
                select(e.PersonalFact)
                .where(
                    e.PersonalFact.statement == item.text,
                    e.PersonalFact.archived_at.is_(None),
                    e.PersonalFact.status.in_([FactStatus.PROPOSED, FactStatus.VERIFIED]),
                )
                .order_by(e.PersonalFact.id)
                .limit(1)
            )
            if fact is None:
                fact = e.PersonalFact(
                    statement=item.text,
                    category={
                        "education": "education",
                        "experience": "experience",
                        "projects": "project",
                        "skills": "skill",
                        "summary": "general",
                    }[section.name],
                    source_locator=f"profile-input:{profile.id}:{section.name}:{item.ordering}",
                )
                session.add(fact)
                await session.flush()
            if fact.status != FactStatus.VERIFIED:
                await verify_user_fact(session, fact.id)
            ids.add(fact.id)
    return ids
