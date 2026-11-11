"""Real isolated PostgreSQL/FastAPI backend for the Profile browser suite. Never production DB."""

import asyncio
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4

import uvicorn
from alembic import command
from alembic.config import Config
from fastapi import Response
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from career_agent.api.app import create_app
from career_agent.config import Settings
from career_agent.infrastructure.db import Base

name = "career_browser_" + uuid4().hex
admin_url = "postgresql+asyncpg://career:career_local_only@127.0.0.1:55432/postgres"
url = admin_url.rsplit("/", 1)[0] + "/" + name


async def admin(sql):
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text(sql))
    finally:
        await engine.dispose()


asyncio.run(admin(f'CREATE DATABASE "{name}"'))
try:
    config = Config("../alembic.ini")
    config.set_main_option("script_location", "../migrations")
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    with tempfile.TemporaryDirectory(prefix="career-profile-browser-") as directory:
        app = create_app(
            Settings(
                database_url=SecretStr(url),
                data_dir=Path(directory),
                live_enabled=False,
                ops_token=SecretStr("synthetic-profile-browser-token"),
            )
        )

        # Real API/DB/Gateway paths with an explicitly offline test-only model adapter.
        from career_agent.models.gateway import ModelGateway
        from career_agent.preparation.providers import POLICY, FixtureTaskProvider, registry
        from career_agent.preparation.research import FixtureResearchAdapter

        release = asyncio.Event()
        release.set()
        entered = asyncio.Event()
        calls = []
        invalid_fit = False
        mock_fault = None
        mock_plan = []
        review_fault = None

        @app.post("/__provider/review-fault")
        async def fail_review(
            kind: Literal["invalid_group", "invalid_evidence", "unknown", "save_failed", "none"],
        ):
            global review_fault
            review_fault = None if kind == "none" else kind
            return {"configured": True}

        @app.post("/__provider/mock-plan")
        async def plan_mock(choices: list[Literal["primary", "follow_up", "finish"]]):
            mock_plan[:] = choices
            return {"configured": len(choices)}

        @app.post("/__provider/mock-fault")
        async def fail_mock(
            kind: Literal[
                "provider_timeout",
                "execution_outcome_unknown",
                "artifact_save_failed",
                "answer_save_failed",
            ],
        ):
            global mock_fault
            mock_fault = kind
            return {"configured": True}

        from sqlalchemy.exc import OperationalError

        from career_agent.evaluation import recording
        from career_agent.infrastructure.entities import ModelCall

        original_bind = recording.bind_artifact

        async def bind_with_fault(session, call_id, *args, **kwargs):
            global mock_fault, review_fault
            call = await session.get(ModelCall, call_id)
            if review_fault == "save_failed" and call.task_type.startswith("interview_"):
                review_fault = None
                raise OperationalError("synthetic debrief persistence failure", {}, None)
            if (
                mock_fault == "artifact_save_failed"
                and call.task_type == "mock_interview_turn_generation"
            ):
                mock_fault = None
                raise OperationalError("synthetic turn persistence failure", {}, None)
            return await original_bind(session, call_id, *args, **kwargs)

        recording.bind_artifact = bind_with_fault

        from sqlalchemy import event
        from sqlalchemy.orm import Session

        from career_agent.infrastructure.entities import MockInterviewTurn

        @event.listens_for(Session, "before_flush")
        def fail_answer_flush(session, flush_context, instances):
            global mock_fault
            if mock_fault == "answer_save_failed" and any(
                isinstance(row, MockInterviewTurn) and row.answer is not None
                for row in session.dirty
            ):
                mock_fault = None
                raise OperationalError("synthetic answer persistence failure", {}, None)

        @app.post("/__provider/hold")
        async def hold():
            calls.clear()
            entered.clear()
            release.clear()
            return {"held": True}

        @app.post("/__provider/release")
        async def unblock():
            release.set()
            return {"released": True}

        @app.get("/__provider/status")
        async def provider_status():
            return {"entered": entered.is_set(), "calls": calls}

        @app.post("/__provider/invalid-fit")
        async def fail_fit():
            global invalid_fit
            invalid_fit = True
            return {"invalid": True}

        class BrowserFixture(FixtureTaskProvider):
            async def generate(self, candidate, context, task):
                global mock_fault
                calls.append(context.task_type)
                entered.set()
                await release.wait()
                if review_fault == "unknown" and context.task_type.startswith("interview_"):
                    from career_agent.models.contracts import ModelGatewayError

                    raise ModelGatewayError("execution_outcome_unknown", retryable=False)
                if context.task_type == "mock_interview_turn_generation" and mock_fault in {
                    "provider_timeout",
                    "execution_outcome_unknown",
                }:
                    from career_agent.models.contracts import ModelGatewayError

                    code, mock_fault = mock_fault, None
                    raise ModelGatewayError(code)
                if context.task_type not in {
                    "company_research_synthesis",
                    "job_requirement_extraction",
                    "fit_analysis",
                }:
                    await asyncio.sleep(0.5)
                response = await super().generate(candidate, context, task)
                if (
                    review_fault == "invalid_group"
                    and context.task_type == "interview_group_debrief"
                ):
                    response.output = {}
                if (
                    review_fault == "invalid_evidence"
                    and context.task_type == "interview_overall_debrief"
                ):
                    response.output["strengths"] = [
                        {"content": "能够说明验证方法。", "evidence": ["99"]}
                    ]
                if context.task_type == "mock_interview_turn_generation" and mock_plan:
                    choice = mock_plan.pop(0)
                    response.output = (
                        {"action": "finish", "turn": None}
                        if choice == "finish"
                        else {
                            "action": "ask",
                            "turn": {
                                "kind": choice,
                                "question": "请说明这项方案如何验证。",
                                "question_type": "technical",
                                "primary_entry_id": task.inputs["policy"]["current_primary_id"]
                                if choice == "follow_up"
                                else None,
                                "requirement_refs": [],
                                "fact_refs": [],
                                "reason_code": "clarify_answer"
                                if choice == "follow_up"
                                else "next_primary",
                            },
                        }
                    )
                if invalid_fit and context.task_type == "fit_analysis":
                    response.output["items"][0]["requirement_ref"] = str(uuid4())
                return response

        @asynccontextmanager
        async def fixture_dependencies(settings, mode):
            yield (
                ModelGateway(registry(settings, False), POLICY, {"fixture": BrowserFixture()}),
                FixtureResearchAdapter(),
            )

        app.state.preparation_dependencies = fixture_dependencies

        @app.post("/__reset")
        async def reset():
            global invalid_fit, mock_fault, review_fault
            invalid_fit = False
            mock_fault = None
            review_fault = None
            release.set()
            entered.clear()
            calls.clear()
            async with app.state.sessions.begin() as session:
                for table in reversed(Base.metadata.sorted_tables):
                    if table.name == "control_events":
                        await session.execute(text("TRUNCATE control_events"))
                    else:
                        await session.execute(table.delete())
            return Response(status_code=204)

        uvicorn.run(app, host="127.0.0.1", port=3131, access_log=False, log_level="error")
finally:
    asyncio.run(admin(f'DROP DATABASE "{name}" WITH (FORCE)'))
