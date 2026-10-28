"""Naming branches are independent of immutable parent and Profile provenance."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.infrastructure import entities as e
from career_agent.product.entities import ProductDraft


async def branch(session: AsyncSession, source: e.ResumeVariantRevision) -> dict[str, Any]:
    state = source.library_state or {}
    if state.get("branch_id"):
        return {k: state[k] for k in ("branch_id", "branch_name")}
    # Legacy adopted refinements already persisted root identity/name/ordinal.
    # Use those facts, never parse a suffix or infer membership from a Profile.
    origin = await session.scalar(
        select(ProductDraft).where(
            ProductDraft.adopted["resume_revision_id"].astext == str(source.id),
            ProductDraft.task == "resume_refinement",
        )
    )
    adoption = (origin.adopted or {}) if origin else {}
    old_name = adoption.get("refinement_root_name")
    old_number = adoption.get("refinement_number")
    if old_name and source.display_name == f"{old_name[:175]} · AI优化版{old_number}":
        value = {"branch_id": adoption["refinement_root_revision_id"], "branch_name": old_name}
    else:
        value = {"branch_id": str(source.id), "branch_name": source.display_name or "简历"}
    source.library_state = {**state, **value}
    return value
