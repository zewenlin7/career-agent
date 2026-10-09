from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from career_agent.application import services
from career_agent.domain.schemas import JobCreate
from career_agent.infrastructure import entities as e
from career_agent.infrastructure.db import Base

pytestmark = pytest.mark.integration


async def test_migration_tables_and_no_drift(sessions, migrated_url):
    async with sessions() as session:
        tables = await (await session.connection()).run_sync(lambda c: inspect(c).get_table_names())
        assert set(Base.metadata.tables) <= set(tables)
        assert await session.scalar(text("select version_num from alembic_version"))
        assert "PostgreSQL" in (await session.scalar(text("select version()")))
    # Alembic has its own event loop; call it outside this loop.
    import asyncio

    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = migrated_url
    await asyncio.to_thread(command.check, cfg)


async def test_fk_unique_rollback(sessions):
    async with sessions() as session:
        session.add(e.JobPosting(company_id=uuid4()))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
        assert list(await session.scalars(select(e.JobPosting))) == []
        session.add_all(
            [
                e.PersonalProfile(revision=1, data={"display_name": "Synthetic A"}),
                e.PersonalProfile(revision=1, data={"display_name": "Synthetic B"}),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
        assert list(await session.scalars(select(e.PersonalProfile))) == []


async def test_validated_jsonb_and_constraint(sessions):
    async with sessions() as session:
        session.add(e.PersonalProfile(revision=1, data={"display_name": ""}))
        with pytest.raises(StatementError):
            await session.commit()
        await session.rollback()
        session.add(e.PersonalProfile(revision=0, data={"display_name": "Synthetic"}))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
        session.add(
            e.PersonalFact(statement="Synthetic", category="project", status=e.FactStatus.VERIFIED)
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_restrict_preserves_business_history(sessions, synthetic):
    async with sessions.begin() as session:
        job = await services.create_job(session, JobCreate.model_validate(synthetic["job"]))
        job_id, company_id = job.id, job.company_id
    async with sessions() as session:
        with pytest.raises(IntegrityError):
            await session.execute(delete(e.Company).where(e.Company.id == company_id))
        await session.rollback()
        with pytest.raises(IntegrityError):
            await session.execute(delete(e.JobPosting).where(e.JobPosting.id == job_id))
        await session.rollback()
        assert await session.get(e.JobPosting, job_id)


async def test_runtime_cascade_and_observation_xor(sessions):
    async with sessions.begin() as session:
        run = e.AgentRun(workflow="test")
        session.add(run)
        await session.flush()
        step = e.AgentStep(run_id=run.id, sequence=1, node="test")
        session.add(step)
        await session.flush()
        tool = e.ToolCall(step_id=step.id, tool_name="fixture")
        model = e.ModelCall(step_id=step.id, task_type="parse", provider="fake", model="fixture")
        session.add_all([tool, model])
        await session.flush()
        session.add(e.Observation(tool_call_id=tool.id, status=e.ObservationStatus.OK))
        run_id, tool_id, model_id = run.id, tool.id, model.id
    async with sessions() as session:
        for ids in [{}, {"tool_call_id": tool_id, "model_call_id": model_id}]:
            session.add(e.Observation(status=e.ObservationStatus.ERROR, **ids))
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()
        await session.execute(delete(e.AgentRun).where(e.AgentRun.id == run_id))
        await session.commit()
        for cls in [e.AgentStep, e.ToolCall, e.ModelCall, e.Observation]:
            assert list(await session.scalars(select(cls))) == []


async def test_revision_unique_and_source_restrict(sessions):
    async with sessions.begin() as session:
        source = e.SourceDocument(kind="synthetic", data_ref="fixture:source")
        session.add(source)
        await session.flush()
        fact = e.PersonalFact(statement="Synthetic", category="test", source_document_id=source.id)
        session.add(fact)
        await session.flush()
        source_id, lineage = source.id, fact.lineage_id
    async with sessions() as session:
        session.add(
            e.PersonalFact(statement="Duplicate", category="test", lineage_id=lineage, revision=1)
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
        with pytest.raises(IntegrityError):
            await session.execute(delete(e.SourceDocument).where(e.SourceDocument.id == source_id))
        await session.rollback()


async def test_runtime_rejects_private_metadata(sessions):
    from pydantic import ValidationError

    async with sessions() as session:
        session.add(e.AgentRun(workflow="test", stop_reason="/private/example/resume.txt"))
        with pytest.raises(ValidationError):
            await session.commit()
        await session.rollback()
        session.add(e.AgentRun(workflow="test", requested_outputs=["synthetic@example.invalid"]))
        with pytest.raises(StatementError):
            await session.commit()
        await session.rollback()


async def test_star_story_validated_structure(sessions):
    async with sessions.begin() as session:
        session.add(
            e.StarStory(
                title="Synthetic STAR",
                data={
                    "situation": "Synthetic setting",
                    "task": "Build API",
                    "action": "Wrote Python",
                    "result": "Delivered test API",
                    "fact_ids": [],
                },
            )
        )
    async with sessions() as session:
        assert (await session.scalar(select(e.StarStory))).data["action"] == "Wrote Python"
