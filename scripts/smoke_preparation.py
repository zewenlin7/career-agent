"""Small explicit smoke, isolated synthetic database; fixture mode makes no network API calls."""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from career_agent.api.app import create_app
from career_agent.application import resumes, services
from career_agent.config import Settings
from career_agent.domain.schemas import Experience, FactCreate, JobCreate, ProfileData, ProfileWrite
from career_agent.infrastructure import entities as e
from career_agent.models.contracts import ModelGatewayError
from career_agent.resume.schemas import ResumeDocument


async def smoke(settings, live):
    if live and (
        not settings.live_enabled or not settings.openai_api_key or not settings.tavily_api_key
    ):
        raise ModelGatewayError("live_configuration_required")
    if live:
        settings = settings.model_copy(
            update={"model_retry_limit": 0, "schema_repair_limit": 0, "research_fail_fast": True}
        )
    output = settings.data_dir / "preparation-smoke" / uuid4().hex
    output.mkdir(parents=True, mode=0o700)
    # Never migrate, truncate or drop the configured application database.
    server = make_url(settings.database_url.get_secret_value()).set(database="postgres")
    name = "career_smoke_" + uuid4().hex
    url = server.set(database=name).render_as_string(hide_password=False)
    admin = create_async_engine(
        server, isolation_level="AUTOCOMMIT", poolclass=NullPool, hide_parameters=True
    )
    engine = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
    summary = {"mode": "live" if live else "fixture", "status": "failed", "runs": []}
    created = False
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
            created = True
        cfg = Config("alembic.ini")
        cfg.attributes["database_url"] = url
        await asyncio.to_thread(command.upgrade, cfg, "head")
        local = settings.model_copy(update={"database_url": SecretStr(url), "data_dir": output})
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        fixture = json.loads(
            await asyncio.to_thread(
                Path("tests/fixtures/resumes/normal_one_page_zh_cn.json").read_text
            )
        )
        async with sessions.begin() as session:
            ids = []
            for item in fixture["facts"]:
                fact = await services.create_fact(
                    session, FactCreate(statement=item["statement"], category="synthetic_smoke")
                )
                # Explicit script invocation confirms ONLY repository synthetic fixture facts.
                await services.verify_user_fact(session, fact.id)
                ids.append(fact.id)
            profile = await services.put_profile(
                session,
                ProfileWrite(
                    expected_revision=0,
                    data=ProfileData(
                        display_name=fixture["name"],
                        projects=[Experience(organization="合成项目", role="开发", fact_ids=ids)],
                    ),
                ),
            )
            job = await services.create_job(
                session,
                JobCreate(
                    company_name="OpenAI",
                    title="合成后端工程师岗位（非真实招聘）",
                    jd_text=(
                        "负责 Python / FastAPI 服务开发。必须具备 PostgreSQL 事务与自动化测试经验。"
                        "了解 RAG / Agent 应用优先。"
                    ),
                ),
            )
            revision = await session.scalar(
                select(e.JobRevision).where(e.JobRevision.job_id == job.id)
            )
            base = await resumes.create_variant(
                session,
                ResumeDocument.model_validate(
                    {
                        "profile_id": str(profile.id),
                        "profile_revision": profile.revision,
                        "job_revision_id": str(revision.id),
                        "sections": [
                            {
                                "section_id": str(uuid4()),
                                "name": "projects",
                                "priority": 80,
                                "ordering": 0,
                                "items": [
                                    {
                                        "item_id": str(uuid4()),
                                        "kind": "bullet",
                                        "text": fixture["facts"][0]["statement"],
                                        "fact_refs": [str(ids[0])],
                                        "priority": 80,
                                        "ordering": 0,
                                    }
                                ],
                            }
                        ],
                    }
                ),
            )
            payload = {
                "profile_id": str(profile.id),
                "resume_revision_id": str(base.id),
                "job_revision_id": str(revision.id),
                "mode": summary["mode"],
                "limits": {"max_estimated_cost": "0.60", "max_model_calls": 8},
            }
        app = create_app(local)
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://local-smoke"
            ) as client:
                for workflow in ["prepare_application", "prepare_interview"]:
                    response = await client.post(f"/api/v1/workflows/{workflow}", json=payload)
                    if response.status_code != 201:
                        raise ModelGatewayError("smoke_request_failed")
                    result = response.json()
                    calls = (
                        await client.get(f"/api/v1/runs/{result['state']['run_id']}/calls")
                    ).json()
                    summary["runs"].append(
                        {"workflow": workflow, "state": result["state"], "calls": calls}
                    )
                    if result["state"]["status"] != "completed":
                        raise ModelGatewayError(result["state"]["stop_reason"] or "smoke_partial")
                    if workflow == "prepare_application":
                        payload["application_package_id"] = result["package_id"]
                        payload["limits"] = {"max_estimated_cost": "0.20", "max_model_calls": 2}
        summary["status"] = "completed"
    except ModelGatewayError as exc:
        summary["error_code"] = exc.code
    except Exception:
        # Do not print SDK/SQL exception bodies, credentials or local paths.
        summary["error_code"] = "smoke_failed"
    finally:
        await engine.dispose()
        if created and live:
            summary["database_ref"] = name  # Keep private domain results for targeted follow-up.
        if created and not live:
            async with admin.connect() as connection:
                await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()
        report = output / "summary.json"
        report.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        report.chmod(0o600)
    print(
        f"mode={summary['mode']} status={summary['status']}; report under "
        f"CAREER_AGENT_DATA_DIR/preparation-smoke/{output.name}/summary.json"
    )
    return 0 if summary["status"] == "completed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicit paid two-workflow smoke; total estimated cap USD 0.80",
    )
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(smoke(Settings(), args.live)))
    except ModelGatewayError as exc:
        raise SystemExit(exc.code) from None


if __name__ == "__main__":
    main()
