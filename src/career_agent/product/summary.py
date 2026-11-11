"""Read-only Summary projection and auditable user entry edits."""

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_agent.application.services import check_revision, read_application, require
from career_agent.domain.rules import DomainError, application_status
from career_agent.domain.schemas import ApplicationEntryWrite
from career_agent.infrastructure import entities as e
from career_agent.product import bindings
from career_agent.product.entities import MaterialSubmission


async def entry_kind(session: AsyncSession, event: e.ApplicationEvent) -> str:
    if event.kind == "created":
        return "created"
    linked = await session.scalar(
        select(MaterialSubmission.id).where(MaterialSubmission.event_id == event.id)
    )
    if linked or event.source == "submission":
        return "system_status" if event.kind in {"status_changed", "correction"} else "system"
    if event.kind in {"status_changed", "correction"}:
        return "status"
    return "note" if event.source == "user_note" else "unknown"


async def entries(session: AsyncSession, id: UUID) -> dict[str, Any]:
    result: dict[str, Any] = {"notes": [], "records": []}
    events = await session.scalars(
        select(e.ApplicationEvent)
        .where(e.ApplicationEvent.application_id == id)
        .order_by(e.ApplicationEvent.created_at.desc(), e.ApplicationEvent.sequence.desc())
    )
    for event in events:
        kind = await entry_kind(session, event)
        if kind not in {"note", "created", "status", "system_status"}:
            continue
        edit = await session.scalar(
            select(e.ApplicationEntryEdit)
            .where(e.ApplicationEntryEdit.event_id == event.id)
            .order_by(e.ApplicationEntryEdit.revision.desc())
            .limit(1)
        )
        if edit and edit.removed:
            continue
        result["notes" if kind == "note" else "records"].append(
            {
                "id": event.id,
                "kind": "status" if kind == "system_status" else kind,
                "text": edit.text if edit else event.note,
                "status": application_status(event.to_status) if event.to_status else None,
                "created_at": event.created_at,
                "revision": edit.revision if edit else 1,
                "editable": kind in {"note", "status"},
            }
        )
    return result


async def edit_entry(
    session: AsyncSession,
    application_id: UUID,
    id: UUID,
    payload: ApplicationEntryWrite,
    *,
    remove: bool = False,
) -> dict[str, Any]:
    app = await require(session, e.Application, application_id, lock=True)
    event = await require(session, e.ApplicationEvent, id)
    if event.application_id != application_id:
        raise DomainError("not_found", 404)
    kind = await entry_kind(session, event)
    if kind not in {"note", "status"}:
        raise DomainError("entry_read_only", 409)
    digest = hashlib.sha256(
        json.dumps(
            {"event": str(id), "remove": remove, "payload": payload.model_dump(mode="json")},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    receipt = await session.scalar(
        select(e.ApplicationEntryEdit).where(
            e.ApplicationEntryEdit.request_id == payload.request_id
        )
    )
    if receipt:
        if receipt.request_hash != digest:
            raise DomainError("idempotency_conflict")
        return {"revision": app.revision}
    check_revision(app.revision, payload.expected_revision)
    latest = await session.scalar(
        select(e.ApplicationEntryEdit)
        .where(e.ApplicationEntryEdit.event_id == id)
        .order_by(e.ApplicationEntryEdit.revision.desc())
        .limit(1)
    )
    revision = latest.revision if latest else 1
    check_revision(revision, payload.expected_entry_revision)
    if latest and latest.removed:
        raise DomainError("not_found", 404)
    text = (payload.text or "").strip() or None
    if not remove and kind == "note" and text is None:
        raise DomainError("note_required", 422)
    if not remove and text == (latest.text if latest else event.note):
        return {"revision": app.revision}
    session.add(
        e.ApplicationEntryEdit(
            event_id=id,
            request_id=payload.request_id,
            request_hash=digest,
            revision=revision + 1,
            text=text,
            removed=remove,
        )
    )
    app.revision += 1
    await session.flush()
    return {"revision": app.revision}


def link(label: str, href: str, time: Any, **extra: Any) -> dict[str, Any]:
    return {"label": label, "href": href, "created_at": time, **extra}


def resume_link(
    row: e.ResumeVariantRevision, pdf: UUID | None = None, current_jd: UUID | None = None
) -> dict[str, Any]:
    href = f"/profile/resumes?revision={row.id}"
    if pdf:
        href += f"&pdf={pdf}"
    return link(
        row.display_name or "简历",
        href,
        row.created_at,
        revision_id=row.id,
        stale=bool(current_jd and row.job_revision_id and row.job_revision_id != current_jd),
    )


async def read(session: AsyncSession, id: UUID) -> dict[str, Any]:
    app = await read_application(session, id)
    binding = await bindings.read(session, id, readonly=True)
    jd = await require(session, e.JobRevision, binding.job_revision_id)
    job = await require(session, e.JobPosting, app.job_id)
    base = f"/applications/{id}"
    result: dict[str, Any] = {
        "revision": app.revision,
        "status": application_status(app.status),
        "jd": {"text": jd.jd_text, "saved_at": jd.created_at, "id": jd.id},
        "resume": None,
        "submission": None,
        "mock": None,
        "actual": {"count": 0, "latest": None},
        "debrief": {"count": 0, "latest": None},
        "preparation": [],
        **await entries(session, id),
    }
    if binding.resume_revision_id:
        result["resume"] = resume_link(
            await require(session, e.ResumeVariantRevision, binding.resume_revision_id),
            current_jd=jd.id,
        )
    research = await session.scalar(
        select(e.CompanyResearch)
        .where(e.CompanyResearch.deleted_at.is_(None))
        .where(e.CompanyResearch.company_id == job.company_id)
        .order_by(e.CompanyResearch.fetched_at.desc(), e.CompanyResearch.id)
        .limit(1)
    )
    result["preparation"].append(
        {
            "kind": "company_research",
            "label": "公司研究",
            "href": base
            + "/research-fit/company"
            + (f"?research={research.id}" if research else ""),
            "created_at": research.fetched_at if research else None,
            "available": research is not None,
            "stale": False,
        }
    )
    from career_agent.product.results import history as task_history

    for target, title, page in [
        ("fit_analysis", "岗位匹配", "research-fit/fit"),
        ("resume_tailoring", "简历优化", "apply/resume"),
        ("greeting_generation", "招呼语", "apply/greeting"),
        ("interview_preparation", "面试准备", "interview/preparation"),
    ]:
        # Successful target artifacts are committed independently from later failed runs.
        history = await task_history(session, id, target, limit=1, offset=0)  # type: ignore[arg-type]
        item = history.items[0] if history.items else None
        result["preparation"].append(
            {
                "kind": target,
                "label": title,
                "href": base
                + "/"
                + page
                + (f"?result={item.result.target_artifact_id}" if item else ""),
                "created_at": item.created_at if item else None,
                "available": item is not None,
                "stale": bool(item and item.result.context.job_revision_id != jd.id),
            }
        )
    submission = await session.scalar(
        select(MaterialSubmission)
        .where(MaterialSubmission.application_id == id, MaterialSubmission.deleted_at.is_(None))
        .order_by(MaterialSubmission.created_at.desc(), MaterialSubmission.id)
        .limit(1)
    )
    if submission:
        greeting = (
            await require(session, e.PreparationArtifact, submission.greeting_id)
            if submission.greeting_id
            else None
        )
        resume = await require(session, e.ResumeVariantRevision, submission.resume_revision_id)
        result["submission"] = {
            "resume": resume_link(resume, submission.render_artifact_id, jd.id),
            "created_at": submission.created_at,
            "greeting": link(
                "招呼语",
                base + f"/apply/greeting?artifact={submission.greeting_id}",
                None,
                stale=bool(greeting and greeting.job_revision_id != jd.id),
            )
            if submission.greeting_id
            else None,
        }
    mocks = list(
        await session.scalars(
            select(e.MockInterviewSession)
            .where(e.MockInterviewSession.application_id == app.id)
            .order_by(e.MockInterviewSession.created_at, e.MockInterviewSession.id)
        )
    )
    if mocks:
        mock = mocks[-1]
        result["mock"] = link(
            f"第 {mock.display_number} 次模拟面试",
            base
            + ("/interview/history" if mock.status == "completed" else "/interview/mock")
            + f"?session={mock.id}",
            mock.created_at,
            status=mock.status,
            completion_type=mock.completion_type,
            stale=bool(
                mock.context.get("binding", {}).get("job_revision_id")
                and mock.context["binding"]["job_revision_id"] != str(jd.id)
            ),
        )
    actual = list(
        await session.scalars(
            select(e.InterviewSession)
            .where(
                e.InterviewSession.application_id == id, e.InterviewSession.status == "completed"
            )
            .order_by(e.InterviewSession.created_at.desc(), e.InterviewSession.id)
        )
    )
    if actual:
        result["actual"] = {
            "count": len(actual),
            "latest": link(
                actual[0].round_name,
                base + f"/interview/history?actual={actual[0].id}",
                actual[0].created_at,
            ),
        }
    debriefs = list(
        await session.scalars(select(e.DebriefRun).where(e.DebriefRun.root_run_id.is_(None)))
    )
    readable = []
    for root in debriefs:
        snapshot = root.snapshot
        source_id = snapshot.get("interview_id")
        names = {str(a.id): a.round_name for a in actual} | {
            str(m.id): f"第 {m.display_number} 次模拟面试" for m in mocks
        }
        if source_id not in names:
            continue
        generations = list(
            await session.scalars(
                select(e.DebriefRun)
                .where(
                    (e.DebriefRun.id == root.id) | (e.DebriefRun.root_run_id == root.id),
                    e.DebriefRun.deleted_at.is_(None),
                )
                .order_by(e.DebriefRun.created_at.desc(), e.DebriefRun.id)
            )
        )
        preferred = root.selected_run_id or root.id
        generations.sort(key=lambda r: r.id != preferred)
        for selected in generations:
            artifacts = list(
                await session.scalars(
                    select(e.DebriefArtifact).where(
                        e.DebriefArtifact.debrief_id == selected.id,
                        e.DebriefArtifact.status == "completed",
                    )
                )
            )
            if not artifacts:
                continue
            completion = await session.scalar(
                select(e.DebriefEvent)
                .where(
                    e.DebriefEvent.debrief_id == selected.id,
                    e.DebriefEvent.data["event"].astext.in_(
                        ["group_completed", "overall_completed", "run_completed", "run_partial"]
                    ),
                )
                .order_by(e.DebriefEvent.created_at.desc(), e.DebriefEvent.sequence.desc())
                .limit(1)
            )
            parent = await require(session, e.AgentRun, selected.run_id)
            time = completion.created_at if completion else parent.finished_at
            readable.append(
                link(
                    names[source_id] + " · 复盘",
                    base + f"/review/debriefs?debrief={selected.id}",
                    time,
                    id=str(selected.id),
                    stale=bool(
                        (selected.snapshot.get("context") or {})
                        .get("binding", {})
                        .get("job_revision_id")
                        and selected.snapshot["context"]["binding"]["job_revision_id"] != str(jd.id)
                    ),
                )
            )
            break
    readable.sort(
        key=lambda x: (x["created_at"].isoformat() if x["created_at"] else "", x["id"]),
        reverse=True,
    )
    result["debrief"] = {"count": len(readable), "latest": readable[0] if readable else None}
    return result
