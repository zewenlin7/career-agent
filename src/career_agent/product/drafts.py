"""Review-first model drafts. Execution uses the existing attempt/budget boundary."""

import asyncio
from functools import partial
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from career_agent.application import resumes
from career_agent.application.services import check_revision, create_fact, put_profile, require
from career_agent.config import Settings
from career_agent.domain.rules import DomainError, FactStatus, RunStatus
from career_agent.domain.schemas import FactCreate, ProfileData, ProfileWrite
from career_agent.evaluation.recording import bind_artifact
from career_agent.infrastructure import entities as e
from career_agent.infrastructure.claims import claim
from career_agent.interview.calls import InterviewCalls, validate_accepted_call
from career_agent.interview.context import digest, freeze
from career_agent.interview.contracts import ContextBinding, InterviewLimits
from career_agent.interview.policy import CallPolicy
from career_agent.interview.validation import safe_prose
from career_agent.models.contracts import ModelGatewayError
from career_agent.models.gateway import ModelGateway
from career_agent.preparation.contracts import (
    GreetingOutput,
    InterviewOutput,
    PrivateResult,
    TargetArtifact,
)
from career_agent.preparation.guardrails import validate_greeting, validate_interview
from career_agent.product.draft_contracts import (
    DraftAdopt,
    DraftCreate,
    FactProposals,
    ResumeExpressions,
)
from career_agent.product.entities import ProductDraft
from career_agent.product.prompts import TASK_SCHEMAS
from career_agent.profile_area.contracts import ResumeDraftData
from career_agent.profile_area.entities import ResumeWorkspace
from career_agent.profile_area.service import draft_document, publish_data
from career_agent.resume.grounding import FactEvidence, numbers, validate_grounding
from career_agent.resume.presentation import Presentation, section_rank
from career_agent.resume.schemas import FactSnapshot, InputSnapshot, ResumeDocument
from career_agent.security.model_view import model_view

TARGETS = {
    "resume_refinement": "resume_tailoring",
    "greeting_refinement": "greeting_generation",
    "interview_preparation_refinement": "interview_preparation",
}


def expressions_document(value: ResumeExpressions, context: dict[str, Any]) -> ResumeDraftData:
    import copy

    source = copy.deepcopy(context["source_document"])
    items = {i["item_id"]: i for sec in source["sections"] for i in sec["items"]}
    ids = [str(i.source_item_id) for i in value.items]
    if len(ids) != len(set(ids)) or set(ids) != set(items):
        raise ModelGatewayError("invalid_resume_source")
    for expression in value.items:
        item = items[str(expression.source_item_id)]
        from career_agent.resume.renderer import rebound_layout

        item["layout"] = rebound_layout(item, expression.text)
        item["text"], item["short_text"] = expression.text, expression.short_text
    for sec in source["sections"]:
        sec["ordering"] = section_rank(sec["name"])
    source["sections"].sort(key=lambda sec: sec["ordering"])
    return ResumeDraftData.model_validate(source)


def validate_output(value: BaseModel, context: dict[str, Any]) -> None:
    if isinstance(value, ResumeExpressions):
        value = expressions_document(value, context)
    facts = {UUID(f["id"]): f for f in context["facts"]}
    if isinstance(value, FactProposals):
        seen = set()
        for proposal in value.facts:
            entries = context.get("extraction_entries", context["profile"]).get(
                proposal.section, []
            )
            if proposal.entry_index >= len(entries):
                raise ModelGatewayError("invalid_fact_source")
            entry = entries[proposal.entry_index]
            if not isinstance(entry, dict):
                raise ModelGatewayError("invalid_fact_source")
            source = " · ".join(
                str(entry[k])
                for k in [
                    "organization",
                    "role",
                    "degree",
                    "major",
                    "start_date",
                    "end_date",
                    "technology_stack",
                    "description",
                    "achievements",
                ]
                if entry.get(k)
            )
            if proposal.statement != proposal.source_quote or proposal.source_quote not in source:
                raise ModelGatewayError("unsupported_fact_proposal")
            key = (proposal.section, proposal.entry_index, proposal.statement)
            if key in seen:
                raise ModelGatewayError("duplicate_fact_proposal")
            seen.add(key)
            safe_prose(proposal.statement, require_chinese=False)
    elif isinstance(value, ResumeDraftData):
        source_items = {
            i["item_id"]: i for sec in context["source_document"]["sections"] for i in sec["items"]
        }
        source_sections = {sec["section_id"]: sec for sec in context["source_document"]["sections"]}
        for sec in value.sections:
            source_section = source_sections.get(str(sec.section_id))
            if (
                source_section is None
                or sec.name != source_section["name"]
                or any(
                    str(item.item_id) not in {i["item_id"] for i in source_section["items"]}
                    for item in sec.items
                )
            ):
                raise ModelGatewayError("invalid_resume_source")
        actual = [item for sec in value.sections for item in sec.items]
        if len({str(i.item_id) for i in actual}) != len(actual) or not actual:
            raise ModelGatewayError("invalid_resume_source")
        for draft_item in actual:
            source_item = source_items.get(str(draft_item.item_id))
            if source_item is None or draft_item.fact_refs != [
                UUID(id) for id in source_item["fact_refs"]
            ]:
                raise ModelGatewayError("invalid_resume_source")
            if not numbers(draft_item.text + (draft_item.short_text or "")) <= numbers(
                source_item["text"]
            ):
                raise ModelGatewayError("grounding_failed")
            if context.get("compression") and (
                draft_item.text != source_item["text"]
                or (
                    draft_item.short_text is not None
                    and numbers(draft_item.short_text) != numbers(source_item["text"])
                )
            ):
                raise ModelGatewayError("compression_not_shorter")
            safe_prose(draft_item.text, require_chinese=False)
        if context.get("compression") and {str(i.item_id) for i in actual} != set(source_items):
            raise ModelGatewayError("compression_required_changed")
    elif isinstance(value, ResumeDocument):
        if (
            str(value.profile_id),
            value.profile_revision,
            str(value.job_revision_id) if value.job_revision_id else None,
        ) != (context["profile_id"], context["profile_revision"], context.get("job_revision_id")):
            raise ModelGatewayError("context_revision_mismatch")
        snapshot = InputSnapshot(
            display_name="",
            facts=[FactSnapshot(fact_id=id, revision=f["revision"]) for id, f in facts.items()],
        )
        if validate_grounding(
            value,
            snapshot,
            set(facts),
            {
                id: FactEvidence(id, f["revision"], FactStatus.VERIFIED, f["statement"])
                for id, f in facts.items()
            },
            {UUID(r["id"]) for r in context.get("requirements", [])},
        ):
            raise ModelGatewayError("grounding_failed")
        for section in value.sections:
            for item in section.items:
                safe_prose(item.text, require_chinese=False)
    elif isinstance(value, GreetingOutput):
        validate_greeting(value, {UUID(r["id"]) for r in context["requirements"]}, facts)
    elif isinstance(value, InterviewOutput):
        validate_interview(
            value,
            {UUID(r["id"]) for r in context["requirements"]},
            set(facts),
            {p["project_ref"] for p in context["profile_refs"]["projects"]},
        )
    else:
        raise ModelGatewayError("output_validation_failed")


def fixture_output(task: str, inputs: dict[str, Any]) -> dict[str, Any]:
    context = inputs["context"]
    if task in {"base_resume_drafting", "resume_library_compression", "resume_claim_refinement"}:
        import copy

        result: dict[str, Any] = copy.deepcopy(context["source_document"])
        if task == "resume_library_compression":
            for sec in result["sections"]:
                for item in sec["items"]:
                    if item.get("short_text"):
                        pass  # Keep full text and the existing compact expression.
                    elif "。" in item["text"]:
                        short = item["text"].split("。")[0] + "。"
                        if len(short) < len(item["text"]):
                            item["short_text"] = short
        return {
            "items": [
                {
                    "source_item_id": i["item_id"],
                    "text": i["text"],
                    "short_text": i.get("short_text"),
                }
                for sec in result["sections"]
                for i in sec["items"]
            ]
        }
    if inputs["original"] is not None:
        return dict(inputs["original"])
    if task == "profile_fact_extraction":
        return {
            "facts": [
                {
                    "section": section,
                    "entry_index": i,
                    "statement": entry["description"],
                    "source_quote": entry["description"],
                }
                for section, entries in context.get(
                    "extraction_entries",
                    {k: context["profile"][k] for k in ("education", "experiences", "projects")},
                ).items()
                for i, entry in enumerate(entries)
                if entry.get("description")
            ]
        }
    document = dict(context["document_template"])
    document["sections"] = [
        {
            "section_id": str(uuid4()),
            "name": "projects",
            "ordering": 0,
            "priority": 80,
            "items": [
                {
                    "item_id": str(uuid4()),
                    "kind": "bullet",
                    "text": f["statement"],
                    "fact_refs": [f["id"]],
                    "priority": 80,
                    "ordering": i,
                }
                for i, f in enumerate(context["facts"][:10])
            ],
        }
    ]
    return ResumeDocument.model_validate(document).model_dump(mode="json")


class DraftService:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], settings: Settings, gateway: ModelGateway
    ):
        self.sessions, self.settings, self.gateway = sessions, settings, gateway
        self.calls = InterviewCalls(sessions, gateway)

    async def context(self, session: AsyncSession, request: DraftCreate) -> dict[str, Any]:
        original = None
        source_resume = None
        extra: dict[str, Any] = {}
        profile_id = request.profile_id
        extraction_workspace = None
        if request.source_workspace_id and request.task == "profile_fact_extraction":
            if request.source_resume_revision_id:
                raise DomainError("invalid_request", 422)
            extraction_workspace = await require(
                session, ResumeWorkspace, request.source_workspace_id
            )
            source_profile = extraction_workspace.profile_id
            if source_profile is None:
                source_profile = (
                    await publish_data(session, extraction_workspace.source, update_current=False)
                ).id
            if profile_id and profile_id != source_profile:
                raise DomainError("context_revision_mismatch", 422)
            profile_id = source_profile
        extraction_resume = None
        if request.source_resume_revision_id:
            if request.task not in {
                "profile_fact_extraction",
                "resume_library_compression",
                "resume_refinement",
            }:
                raise DomainError("invalid_request", 422)
            extraction_resume = await require(
                session, e.ResumeVariantRevision, request.source_resume_revision_id
            )
            if profile_id and profile_id != extraction_resume.profile_id:
                raise DomainError("context_revision_mismatch", 422)
            profile_id = extraction_resume.profile_id
        library_refinement = request.task == "resume_refinement" and not request.source_artifact_id
        if library_refinement:
            if not request.feedback or bool(request.source_workspace_id) == bool(
                request.source_resume_revision_id
            ):
                raise DomainError("refinement_source_required", 422)
            if request.source_workspace_id:
                from career_agent.profile_area.evidence import resolve_claims
                from career_agent.profile_area.service import accept_draft

                await session.execute(text("SELECT pg_advisory_xact_lock(78420101)"))
                work = await require(
                    session, ResumeWorkspace, request.source_workspace_id, lock=True
                )
                if work.archived_at:
                    raise DomainError("resume_archived")
                if not work.accepted_revision_id and await resolve_claims(session, work):
                    raise DomainError("resume_source_required", 422)
                extraction_resume = await accept_draft(session, work)
            assert extraction_resume is not None
            if extraction_resume.archived_at:
                raise DomainError("resume_archived")
            profile_id = extraction_resume.profile_id
            source_resume = extraction_resume.id
            original = extraction_resume.document
            extra = {
                "source_resume_revision_id": str(source_resume),
                "source_workspace_id": str(request.source_workspace_id)
                if request.source_workspace_id
                else None,
                "job_revision_id": str(extraction_resume.job_revision_id)
                if extraction_resume.job_revision_id
                else None,
                "requirements": [],
            }
            if extraction_resume.job_revision_id:
                frozen = await freeze(
                    session,
                    self.settings,
                    self.gateway,
                    ContextBinding(
                        profile_id=profile_id,
                        job_revision_id=extraction_resume.job_revision_id,
                        resume_revision_id=source_resume,
                    ),
                )
                extra = {**frozen.data, **extra, "requirements": frozen.data["requirements"]}
            if request.application_id:
                app = await require(session, e.Application, request.application_id)
                jd = (
                    await require(session, e.JobRevision, extraction_resume.job_revision_id)
                    if extraction_resume.job_revision_id
                    else None
                )
                if jd is None or jd.job_id != app.job_id:
                    raise DomainError("context_revision_mismatch", 422)
            if request.feedback_id:
                from career_agent.evaluation.entities import FeedbackRow

                feedback_row = await require(session, FeedbackRow, request.feedback_id)
                if feedback_row.subject_id not in {source_resume, request.source_workspace_id}:
                    raise DomainError("feedback_source_mismatch", 422)
        if request.task in TARGETS and not library_refinement:
            if not request.source_artifact_id or not request.feedback:
                raise DomainError("refinement_source_required", 422)
            source = await require(session, e.PreparationArtifact, request.source_artifact_id)
            target = PrivateResult.model_validate(source.data).output
            if not isinstance(target, TargetArtifact) or target.target != TARGETS[request.task]:
                raise DomainError("context_revision_mismatch", 422)
            if request.application_id:
                application = await require(session, e.Application, request.application_id)
                jd = await require(session, e.JobRevision, source.job_revision_id)
                if application.job_id != jd.job_id:
                    raise DomainError("context_revision_mismatch", 422)
            if request.feedback_id:
                from career_agent.evaluation.entities import FeedbackRow

                feedback_row = await require(session, FeedbackRow, request.feedback_id)
                if feedback_row.subject_id not in {target.resume_revision_id, target.result_id}:
                    raise DomainError("feedback_source_mismatch", 422)
            profile_id = source.profile_id
            source_resume = target.resume_revision_id or target.source_resume_revision_id
            if source_resume is None:
                raise DomainError("resume_selection_required", 422)
            frozen = await freeze(
                session,
                self.settings,
                self.gateway,
                ContextBinding(
                    profile_id=source.profile_id,
                    job_revision_id=source.job_revision_id,
                    resume_revision_id=source_resume,
                ),
            )
            extra = {
                **frozen.data,
                "source_artifact_id": str(source.id),
                "job_revision_id": str(source.job_revision_id),
                "source_resume_revision_id": str(source_resume),
            }
            if target.resume_revision_id:
                original = (
                    await require(session, e.ResumeVariantRevision, target.resume_revision_id)
                ).document
            elif target.result_id:
                original = (await require(session, e.PreparationArtifact, target.result_id)).data[
                    "output"
                ]
        library_source = None
        if request.task in {"resume_library_compression", "resume_claim_refinement"}:
            if request.source_workspace_id:
                library_source = await require(
                    session, ResumeWorkspace, request.source_workspace_id
                )
                profile_id = library_source.profile_id
            if (request.task == "resume_claim_refinement" and not request.selected_item_ids) or (
                library_source is None and extraction_resume is None
            ):
                raise DomainError("resume_selection_required", 422)
        if profile_id is None:
            raise DomainError("profile_required", 422)
        profile = await require(session, e.PersonalProfile, profile_id)
        data = ProfileData.model_validate(profile.data)
        facts = list(
            await session.scalars(
                select(e.PersonalFact)
                .where(
                    e.PersonalFact.id.in_(resumes.profile_fact_ids(profile)),
                    e.PersonalFact.status == FactStatus.VERIFIED,
                )
                .order_by(e.PersonalFact.id)
            )
        )
        extraction_source = extraction_workspace or extraction_resume
        if extraction_source and request.task == "profile_fact_extraction":
            # The same governed extraction task receives literal resume-source entries.
            # It never sees a mutable/latest resume or infers a different profile binding.
            extra["extraction_entries"] = {
                {
                    "experience": "experiences",
                    "projects": "projects",
                    "education": "education",
                    "skills": "skills",
                    "summary": "summary",
                }[section["name"]]: [{"description": item["text"]} for item in section["items"]]
                for section in extraction_source.document["sections"]
            }
            extra["extraction_source"] = {
                "kind": "resume_workspace" if extraction_workspace else "resume",
                "id": str(extraction_source.id),
                "revision": extraction_source.revision,
            }
        if (
            request.task
            not in {
                "profile_fact_extraction",
                "base_resume_drafting",
                "resume_library_compression",
                "resume_claim_refinement",
            }
            and not facts
        ):
            raise DomainError("verified_facts_required", 422)
        context = {
            **extra,
            "profile_id": str(profile.id),
            "profile_revision": profile.revision,
            "profile": data.model_dump(mode="json"),
            "facts": [
                {"id": str(f.id), "revision": f.revision, "statement": f.statement} for f in facts
            ],
            "document_template": {
                "profile_id": str(profile.id),
                "profile_revision": profile.revision,
                "job_revision_id": None,
            },
        }
        if request.task == "base_resume_drafting":
            from uuid import uuid5

            source_doc = draft_document(data).model_dump(mode="json")
            for sec in source_doc["sections"]:
                sec["section_id"] = str(uuid5(profile.id, sec["name"]))
                for index, item in enumerate(sec["items"]):
                    item["item_id"] = str(uuid5(profile.id, f"{sec['name']}:{index}"))
                    item["fact_refs"] = [
                        ref for ref in item["fact_refs"] if ref in {str(f.id) for f in facts}
                    ]
            context["source_document"] = source_doc
        elif request.task in {"resume_library_compression", "resume_claim_refinement"}:
            assert library_source is not None or extraction_resume is not None
            source_doc = library_source.document if library_source else extraction_resume.document  # type: ignore[union-attr]
            subset = ResumeDraftData.model_validate({"sections": source_doc["sections"]})
            chosen = set(request.selected_item_ids)
            all_ids = {i.item_id for sec in subset.sections for i in sec.items}
            if request.task == "resume_library_compression":
                compression_source = library_source or extraction_resume
                assert compression_source is not None
                presentation = Presentation.model_validate(compression_source.presentation or {})
                chosen = {
                    item.item_id
                    for sec in subset.sections
                    for item in sec.items
                    if sec.name not in presentation.hidden_sections
                    and item.item_id not in presentation.hidden_item_ids
                    and not item.short_text
                }
                if not chosen:
                    raise DomainError("compression_not_needed", 422)
            if not chosen <= all_ids:
                raise DomainError("invalid_request", 422)
            for sec in subset.sections:
                sec.items = [i for i in sec.items if i.item_id in chosen]
            subset.sections = [s for s in subset.sections if s.items]
            if request.task == "resume_claim_refinement":
                if library_source is None:
                    raise DomainError("resume_selection_required", 422)
                original = subset.model_dump(mode="json")
                evidence = library_source.content_sources or {}
                for sec in subset.sections:
                    for item in sec.items:
                        statement = evidence.get(str(item.item_id), {}).get("statement")
                        if not statement:
                            raise DomainError("resume_source_required", 422)
                        item.text, item.short_text = statement, None
            context["source_document"] = subset.model_dump(mode="json")
            context["compression"] = request.task == "resume_library_compression"
            context["profile"] = {}  # Only the selected content goes to this model call.
            context["facts"] = []
        return {
            "context": model_view(context, name=data.display_name),
            "original": model_view(original, name=data.display_name),
            "feedback": model_view(request.feedback, name=data.display_name),
        }

    async def create(self, request: DraftCreate) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            await claim(session, "product-draft:" + str(request.request_id))
            existing = await session.scalar(
                select(ProductDraft).where(ProductDraft.request_id == request.request_id)
            )
            if existing:
                if existing.request != request.model_dump(mode="json"):
                    raise DomainError("idempotency_conflict")
                return self.view(existing)
            inputs = await self.context(session, request)
            limits = InterviewLimits(
                max_model_calls=1
                + self.settings.model_retry_limit
                + self.settings.schema_repair_limit,
                max_estimated_cost=self.settings.max_run_cost,
            )
            run = e.AgentRun(
                workflow="product_drafting",
                workflow_version="product-drafting-v1",
                status=RunStatus.PENDING,
                requested_outputs=[request.task],
                budget={
                    "token_limit": limits.max_input_tokens + limits.max_output_tokens,
                    "cost_limit": str(limits.max_estimated_cost),
                },
            )
            session.add(run)
            await session.flush()
            row = ProductDraft(
                request_id=request.request_id,
                run_id=run.id,
                logical_operation_id=uuid4(),
                task=request.task,
                mode=request.mode,
                request=request.model_dump(mode="json"),
                context=inputs,
                limits=limits.model_dump(mode="json"),
            )
            session.add(row)
            await session.flush()
            return self.view(row)

    @staticmethod
    def view(row: ProductDraft) -> dict[str, Any]:
        return {
            "id": row.id,
            "task": row.task,
            "status": row.status,
            "reason": row.reason,
            "output": row.output,
            "adopted": row.adopted,
            "accepted_model_call_id": row.accepted_model_call_id,
            "lineage": {
                "source_artifact_id": row.request.get("source_artifact_id"),
                "source_resume_revision_id": row.context.get("context", {}).get(
                    "source_resume_revision_id"
                ),
                "source_workspace_id": row.request.get("source_workspace_id"),
                "feedback_id": row.request.get("feedback_id"),
                "application_id": row.request.get("application_id"),
                "intent": row.request.get("intent", "refine"),
            },
        }

    async def execute(self, id: UUID) -> dict[str, Any]:
        async with self.sessions.kw["bind"].connect() as lock:
            acquired = await lock.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:key, 4308))"), {"key": str(id)}
            )
            await lock.commit()
            if not acquired:
                raise DomainError("operation_in_progress")
            try:
                async with self.sessions.begin() as session:
                    row = await require(session, ProductDraft, id, lock=True)
                    if row.status == "running":
                        row.status, row.reason = "recovery_required", "execution_interrupted"
                    if row.status != "pending":
                        return self.view(row)
                    # Revalidate facts/context before dispatch; retain original frozen model input.
                    fresh = await self.context(session, DraftCreate.model_validate(row.request))
                    if digest(fresh) != digest(row.context):
                        raise DomainError("context_revision_mismatch")
                    row.status = "running"
                    run = await require(session, e.AgentRun, row.run_id)
                    run.status = RunStatus.RUNNING
                    task, inputs, operation_id = row.task, row.context, row.logical_operation_id
                repairs = transport = 0
                reason = None
                while True:
                    try:
                        accepted = await self.calls.generate(
                            "product_draft",
                            id,
                            task,
                            inputs,
                            CallPolicy(max_estimated_cost=self.settings.max_run_cost),
                            partial(validate_output, context=inputs["context"]),
                            logical_operation_id=operation_id,
                            retry_reason=reason if transport else None,
                            repair_reason="schema_invalid" if repairs else None,
                        )
                        break
                    except ModelGatewayError as exc:
                        if (
                            exc.code in {"structured_output_invalid", "output_validation_failed"}
                            and repairs < self.settings.schema_repair_limit
                        ):
                            repairs += 1
                            inputs = {**inputs, "repair_reason": "schema_invalid"}
                        elif exc.retryable and transport < self.settings.model_retry_limit:
                            transport += 1
                        else:
                            async with self.sessions.begin() as session:
                                row = await require(session, ProductDraft, id, lock=True)
                                row.status, row.reason = "failed", exc.code
                                run = await require(session, e.AgentRun, row.run_id)
                                run.status, run.stop_reason = RunStatus.FAILED, exc.code
                                return self.view(row)
                        reason = exc.code
                async with self.sessions.begin() as session:
                    row = await require(session, ProductDraft, id, lock=True)
                    await validate_accepted_call(session, accepted, row.run_id, operation_id)
                    row.output, row.accepted_model_call_id = (
                        accepted.output.model_dump(mode="json"),
                        accepted.model_call_id,
                    )
                    row.status = "completed"
                    run = await require(session, e.AgentRun, row.run_id)
                    run.status, run.finished_at = RunStatus.COMPLETED, e.utcnow()
                    return self.view(row)
            except asyncio.CancelledError:
                from career_agent.profile_area.cancellation import mark_cancelled

                await mark_cancelled(self.sessions, id)
                raise
            finally:
                await lock.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:key, 4308))"),
                    {"key": str(id)},
                )
                await lock.commit()

    async def adopt(self, id: UUID, request: DraftAdopt) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            row = await require(session, ProductDraft, id, lock=True)
            if row.adopted is not None:
                return self.view(row)
            if (
                row.status != "completed"
                or row.output is None
                or row.accepted_model_call_id is None
            ):
                raise DomainError("result_not_available")
            original_request = DraftCreate.model_validate(row.request)
            current = await self.context(session, original_request)
            if digest(current) != digest(row.context):
                raise DomainError("context_revision_mismatch")
            output: BaseModel
            # Historical completed proposals retain their original canonical schema.
            if (
                row.task
                in {"base_resume_drafting", "resume_library_compression", "resume_claim_refinement"}
                and "sections" in row.output
            ):
                output = ResumeDraftData.model_validate(row.output)
            else:
                output = TASK_SCHEMAS[row.task].model_validate(row.output)
            if isinstance(output, ResumeExpressions):
                output = expressions_document(output, row.context["context"])
            if isinstance(output, ResumeDocument):
                for sec in output.sections:
                    sec.ordering = section_rank(sec.name)
                output.sections.sort(key=lambda sec: sec.ordering)
            validate_output(output, row.context["context"])
            profile = await require(
                session, e.PersonalProfile, UUID(row.context["context"]["profile_id"])
            )
            if row.task == "resume_library_compression":
                assert isinstance(output, ResumeDraftData)
                source = (
                    await require(session, ResumeWorkspace, original_request.source_workspace_id)
                    if original_request.source_workspace_id
                    else await require(
                        session,
                        e.ResumeVariantRevision,
                        UUID(str(original_request.source_resume_revision_id)),
                    )
                )
                # Model views are minimized copies, never authoritative resume bodies.
                # Compression may contribute only short forms keyed by exact source IDs.
                compression_proposal = ResumeDraftData.model_validate(
                    {"sections": source.document["sections"]}
                )
                short_forms = {
                    item.item_id: item.short_text
                    for section in output.sections
                    for item in section.items
                }
                for section in compression_proposal.sections:
                    for item in section.items:
                        if item.item_id not in short_forms:
                            continue
                        short = short_forms[item.item_id]
                        # Do not persist privacy placeholders as user-facing expressions.
                        item.short_text = (
                            None
                            if short
                            and any(
                                marker in short
                                for marker in ("[PERSON]", "[CONTACT]", "[EMAIL]", "[PHONE]")
                            )
                            else short
                        )
                row.adopted = {
                    "resume_edit": {
                        "source_workspace_id": str(original_request.source_workspace_id)
                        if original_request.source_workspace_id
                        else None,
                        "source_resume_revision_id": str(original_request.source_resume_revision_id)
                        if original_request.source_resume_revision_id
                        else None,
                        "document": compression_proposal.model_dump(mode="json"),
                        "presentation": source.presentation or {},
                        "generation_id": str(row.id),
                        "generated_item_ids": [
                            str(i.item_id)
                            for sec in compression_proposal.sections
                            for i in sec.items
                            if i.item_id in short_forms and i.short_text
                        ],
                    }
                }
                return self.view(row)
            if isinstance(output, FactProposals):
                if request.expected_profile_revision is not None:
                    check_revision(profile.revision, request.expected_profile_revision)
                elif request.selected_indices is None:
                    raise DomainError("profile_revision_required", 422)
                data = ProfileData.model_validate(profile.data)
                ids = []
                if request.selected_indices is not None and (
                    len(set(request.selected_indices)) != len(request.selected_indices)
                    or any(i < 0 or i >= len(output.facts) for i in request.selected_indices)
                ):
                    raise DomainError("invalid_request", 422)
                chosen = (
                    range(len(output.facts))
                    if request.selected_indices is None
                    else request.selected_indices
                )
                duplicate_ids = []
                await session.execute(text("SELECT pg_advisory_xact_lock(78420101)"))
                for index in chosen:
                    proposal = output.facts[index]
                    entry = (
                        getattr(data, proposal.section)[proposal.entry_index]
                        if not (
                            original_request.source_resume_revision_id
                            or original_request.source_workspace_id
                        )
                        else None
                    )
                    category = {
                        "experiences": "experience",
                        "projects": "project",
                        "education": "education",
                        "skills": "skill",
                        "summary": "general",
                    }[proposal.section]
                    fact = await session.scalar(
                        select(e.PersonalFact)
                        .where(
                            e.PersonalFact.archived_at.is_(None),
                            e.PersonalFact.statement == proposal.statement,
                            e.PersonalFact.status.in_([FactStatus.PROPOSED, FactStatus.VERIFIED]),
                        )
                        .order_by(e.PersonalFact.id)
                        .limit(1)
                    )
                    if fact is None:
                        fact = await create_fact(
                            session,
                            FactCreate(
                                statement=proposal.statement,
                                category=category,
                                source_locator=(
                                    f"resume:{original_request.source_resume_revision_id}:{proposal.section}:{proposal.entry_index}"
                                    if original_request.source_resume_revision_id
                                    else (
                                        f"resume-draft:{original_request.source_workspace_id}:"
                                        f"{row.context['context']['extraction_source']['revision']}:"
                                        f"{proposal.section}:{proposal.entry_index}"
                                    )
                                    if original_request.source_workspace_id
                                    else (
                                        f"profile:{profile.id}:"
                                        f"{proposal.section}:{proposal.entry_index}"
                                    )
                                ),
                            ),
                        )
                        if entry is not None:
                            entry.fact_ids.append(fact.id)
                    else:
                        duplicate_ids.append(str(fact.id))
                    ids.append(str(fact.id))
                if (
                    request.selected_indices is None
                    and not original_request.source_resume_revision_id
                    and not original_request.source_workspace_id
                ):
                    updated = await put_profile(
                        session,
                        ProfileWrite(
                            expected_revision=request.expected_profile_revision, data=data
                        ),
                    )
                    row.adopted = {"fact_ids": ids, "profile_id": str(updated.id)}
                else:
                    row.adopted = {
                        "fact_ids": ids,
                        "existing_fact_ids": duplicate_ids,
                        "profile_id": str(profile.id),
                    }
                subject = row.id
            elif isinstance(output, ResumeDraftData):
                from career_agent.profile_area.service import next_resume_number

                await session.execute(text("SELECT pg_advisory_xact_lock(78420101)"))
                number = (
                    await next_resume_number(session)
                    if row.task == "base_resume_drafting"
                    else None
                )
                source_data, document = profile.data, output.model_dump(mode="json")
                parent_id = original_request.source_workspace_id
                if row.task in {"resume_library_compression", "resume_claim_refinement"}:
                    if parent_id:
                        parent = await require(session, ResumeWorkspace, parent_id)
                        source_data, full = parent.source, parent.document
                    else:
                        assert original_request.source_resume_revision_id is not None
                        original_resume = await require(
                            session,
                            e.ResumeVariantRevision,
                            original_request.source_resume_revision_id,
                        )
                        full = original_resume.document
                    import copy

                    document = {"sections": copy.deepcopy(full["sections"])}
                    replacements = {
                        i["item_id"]: i
                        for sec in output.model_dump(mode="json")["sections"]
                        for i in sec["items"]
                    }
                    for sec in document["sections"]:
                        for item in sec["items"]:
                            if item["item_id"] in replacements:
                                replacement = replacements[item["item_id"]]
                                item["text"], item["short_text"] = (
                                    replacement["text"],
                                    replacement.get("short_text"),
                                )
                saved_work = ResumeWorkspace(
                    name=(
                        f"简历 {number}"
                        if number is not None
                        else (parent.name if parent_id else original_resume.display_name or "简历")
                    ),
                    number=number,
                    profile_id=profile.id,
                    source=source_data,
                    document=document,
                    parent_id=parent_id,
                    source_resume_revision_id=original_request.source_resume_revision_id
                    or (
                        (parent.accepted_revision_id or parent.source_resume_revision_id)
                        if parent_id
                        else None
                    ),
                    presentation=(
                        parent.presentation
                        if parent_id
                        else (
                            original_resume.presentation
                            if original_request.source_resume_revision_id
                            else {}
                        )
                    ),
                )
                source_items = {
                    i["item_id"]: i
                    for sec in (
                        full["sections"]
                        if row.task == "resume_library_compression"
                        else row.context["context"]["source_document"]["sections"]
                    )
                    for i in sec["items"]
                }
                inherited = (
                    parent.content_sources
                    if parent_id
                    and original_request.task
                    in {"resume_library_compression", "resume_claim_refinement"}
                    and original_request.source_workspace_id
                    else None
                )
                saved_work.content_sources = {
                    i["item_id"]: (inherited or {}).get(
                        i["item_id"],
                        {
                            "kind": "ai",
                            "statement": source_items.get(i["item_id"], {}).get("text", ""),
                        },
                    )
                    for sec in document["sections"]
                    for i in sec["items"]
                }
                session.add(saved_work)
                await session.flush()
                subject = saved_work.id
                row.adopted = {"resume_workspace_id": str(saved_work.id)}
            elif isinstance(output, ResumeDocument):
                refinement_metadata: dict[str, Any] = {}
                source_revision = row.context["context"].get("source_resume_revision_id")
                if source_revision:
                    previous = await require(
                        session, e.ResumeVariantRevision, UUID(source_revision)
                    )
                    variant = await require(
                        session, e.ResumeVariant, previous.resume_variant_id, lock=True
                    )
                    await session.refresh(previous, with_for_update=True)
                    variant.current_revision += 1
                    saved = await resumes.save_revision(session, variant, output)
                    saved.presentation = previous.presentation
                    root = await session.scalar(
                        select(e.ResumeVariantRevision)
                        .where(e.ResumeVariantRevision.resume_variant_id == variant.id)
                        .order_by(e.ResumeVariantRevision.revision)
                        .limit(1)
                    )
                    assert root is not None
                    from career_agent.profile_area.naming import branch

                    naming = await branch(session, previous)
                    branch_id = naming["branch_id"]
                    ordinal = 1 + (
                        await session.scalar(
                            select(func.count())
                            .select_from(ProductDraft)
                            .where(
                                ProductDraft.task == "resume_refinement",
                                or_(
                                    ProductDraft.adopted["refinement_branch_id"].astext
                                    == branch_id,
                                    (
                                        ProductDraft.adopted["refinement_branch_id"].astext.is_(
                                            None
                                        )
                                        & (
                                            ProductDraft.adopted[
                                                "refinement_root_revision_id"
                                            ].astext
                                            == branch_id
                                        )
                                    ),
                                ),
                            )
                        )
                        or 0
                    )
                    saved.library_state = naming
                    saved.display_name = f"{naming['branch_name'][:175]} · AI优化版{ordinal}"
                    refinement_metadata = {
                        "refinement_root_revision_id": str(root.id),
                        "refinement_root_name": root.display_name or "简历",
                        "refinement_branch_id": branch_id,
                        "refinement_branch_name": naming["branch_name"],
                        "refinement_number": ordinal,
                    }
                else:
                    saved = await resumes.create_variant(session, output)
                subject = saved.id
                row.adopted = {
                    "resume_revision_id": str(saved.id),
                    "resume_variant_id": str(saved.resume_variant_id),
                    **refinement_metadata,
                }
            else:
                kind = "greeting" if isinstance(output, GreetingOutput) else "interview"
                result = e.PreparationArtifact(
                    run_id=row.run_id,
                    profile_id=profile.id,
                    job_revision_id=UUID(row.context["context"]["job_revision_id"]),
                    data=PrivateResult(kind=kind, output=output).model_dump(mode="json"),
                )
                session.add(result)
                await session.flush()
                subject = result.id
                row.adopted = {"result_id": str(result.id)}
            if row.task in TARGETS and original_request.source_artifact_id:
                from typing import cast

                from career_agent.application.compatibility import execution_versions
                from career_agent.preparation.contracts import Target

                target_name = cast(Target, TARGETS[row.task])
                target = TargetArtifact(
                    target=target_name,
                    fingerprint=digest({"draft": str(row.id)}),
                    result_id=subject if not isinstance(output, ResumeDocument) else None,
                    resume_revision_id=subject if isinstance(output, ResumeDocument) else None,
                    source_resume_revision_id=UUID(
                        row.context["context"]["source_resume_revision_id"]
                    ),
                    compatibility_versions=execution_versions(target_name),
                )
                wrapper = e.PreparationArtifact(
                    run_id=row.run_id,
                    profile_id=profile.id,
                    job_revision_id=UUID(row.context["context"]["job_revision_id"]),
                    data=PrivateResult(kind="target", output=target).model_dump(mode="json"),
                )
                session.add(wrapper)
                await session.flush()
                row.adopted = {**row.adopted, "target_artifact_id": str(wrapper.id)}
            await bind_artifact(
                session, row.accepted_model_call_id, subject, self.settings.judge_sampling
            )
            return self.view(row)
