"""Freeze explicit context using existing v0.1 exact-context and grounding loaders."""

import hashlib
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import require
from career_agent.config import Settings
from career_agent.domain.rules import DomainError
from career_agent.domain.schemas import ProfileData
from career_agent.infrastructure import entities as e
from career_agent.interview.contracts import ContextBinding, FrozenContext
from career_agent.models.gateway import ModelGateway
from career_agent.preparation.context import ContextLoader
from career_agent.preparation.contracts import (
    InterviewOutput,
    PrivateResult,
    WorkflowRequest,
    WorkflowState,
)
from career_agent.preparation.guardrails import minimize
from career_agent.preparation.research import FixtureResearchAdapter
from career_agent.preparation.workflows import PreparationWorkflow


def digest(data: Any) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def clean(value: Any, name: str = "") -> Any:
    if isinstance(value, str):
        return minimize(value, name)
    if isinstance(value, dict):
        return {k: clean(v, name) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v, name) for v in value]
    return value


async def freeze(
    session: AsyncSession, settings: Settings, gateway: ModelGateway, binding: ContextBinding
) -> FrozenContext:
    runner = PreparationWorkflow(
        session,
        settings,
        gateway,
        FixtureResearchAdapter(),
        WorkflowRequest(
            profile_id=binding.profile_id,
            job_revision_id=binding.job_revision_id,
            resume_revision_id=binding.resume_revision_id,
            targets=["fit_analysis"],
        ),
    )
    runner.state = WorkflowState(
        run_id=uuid4(),
        workflow="prepare_application",
        profile_id=binding.profile_id,
        job_revision_id=binding.job_revision_id,
        requested_outputs=[],
    )
    await runner.validate_inputs()
    if runner.state.warnings:
        raise DomainError("interview_context_too_large", 422)
    loader = ContextLoader(runner)
    runner.requirements = await loader.requirements()
    variant = await loader.resume(binding.resume_revision_id)
    if variant.job_revision_id is not None and variant.job_revision_id != binding.job_revision_id:
        raise DomainError("context_revision_mismatch", 422)
    data: dict[str, Any] = {
        "job": runner.job_context(),
        "requirements": runner.requirements_context(),
        "facts": list(runner.facts.values()),
        "resume": variant.document,
        "profile_refs": runner.profile_refs,
    }
    if binding.interview_preparation_id:
        artifact = await require(session, e.PreparationArtifact, binding.interview_preparation_id)
        parsed = PrivateResult.model_validate(artifact.data)
        package = await session.scalar(
            select(e.PreparationArtifact).where(
                e.PreparationArtifact.run_id == artifact.run_id,
                e.PreparationArtifact.data["kind"].astext == "package",
            )
        )
        state = PrivateResult.model_validate(package.data).output if package else None
        if (
            artifact.profile_id != binding.profile_id
            or artifact.job_revision_id != binding.job_revision_id
            or parsed.kind != "interview"
            or not isinstance(parsed.output, InterviewOutput)
            or not isinstance(state, WorkflowState)
            or state.resume_variant_id != variant.resume_variant_id
            or state.resume_variant_revision != variant.revision
        ):
            raise DomainError("context_revision_mismatch", 422)
        data["interview_preparation"] = parsed.output.model_dump(mode="json")
    name = ProfileData.model_validate(runner.profile.data).display_name
    return FrozenContext(
        binding=binding,
        profile_revision=runner.profile.revision,
        job_id=runner.job.job_id,
        job_revision=runner.job.revision,
        fact_snapshot={f.id: f.revision for f in runner.fact_rows.values()},
        data=clean(data, name),
    )
