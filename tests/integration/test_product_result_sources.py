"""Product source labels follow the exact materials used by each action."""

from uuid import uuid4

import pytest
from test_preparation import prep_input as prep_fixture
from test_product_drafts import draft

prep_input = prep_fixture
pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "target,task,workflow",
    [
        ("resume_tailoring", "resume_refinement", "prepare_application"),
        ("greeting_generation", "greeting_refinement", "prepare_application"),
        ("interview_preparation", "interview_preparation_refinement", "prepare_interview"),
    ],
)
@pytest.mark.parametrize("intent", ["refine", "regenerate"])
async def test_exact_sources_distinguish_generation_from_refinement(
    client, prep_input, target, task, workflow, intent
):
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    job = (await client.get("/api/v1/jobs")).json()[0]
    operation = (
        await client.post(
            f"/api/v1/companies/{job['company_id']}/research",
            json={
                "request_id": str(uuid4()),
                "kind": "company_research",
                "request": {
                    "job_revision_id": prep_input["job_revision_id"],
                    "mode": "fixture",
                    "force_research_refresh": True,
                },
            },
        )
    ).json()
    research = (await client.post(f"/api/v1/operations/{operation['id']}/execute")).json()[
        "research_report_id"
    ]
    generated = await client.post(
        f"/api/v1/workflows/{workflow}",
        json={
            **prep_input,
            **({"targets": [target]} if workflow == "prepare_application" else {}),
        },
    )
    assert generated.status_code == 201, generated.text
    assert generated.json()["outcome"]["status"] == "completed"
    source = generated.json()["outcome"]["targets"][target]["artifact_id"]
    exact_path = f"/api/v1/preparation-artifacts/{source}/result?application_id={app['id']}"
    first = (await client.get(exact_path)).json()["result"]
    assert first["source_resume_revision_id"] == prep_input["resume_revision_id"]
    assert first["source_research_id"] == (None if target == "resume_tailoring" else research)
    assert first["source_profile_id"] == (
        prep_input["profile_id"] if target == "resume_tailoring" else None
    )
    selected_resume = first["resume_revision_id"] or first["source_resume_revision_id"]
    assert first["refinement_resume_revision_id"] == selected_resume
    assert first["refinement_profile_id"] == (
        None if target == "interview_preparation" else prep_input["profile_id"]
    )
    refined = await draft(
        client,
        task,
        source_artifact_id=source,
        application_id=app["id"],
        intent=intent,
        feedback="突出原有项目中的事务测试，不添加新经历。",
    )
    refined_id = refined["adopted"]["target_artifact_id"]
    result = (
        await client.get(
            f"/api/v1/preparation-artifacts/{refined_id}/result?application_id={app['id']}"
        )
    ).json()["result"]
    assert result["source_original_target_id"] == source
    assert result["source_resume_revision_id"] == selected_resume
    assert result["source_research_id"] == (research if target == "interview_preparation" else None)
    assert result["source_profile_id"] == (
        None if target == "interview_preparation" else prep_input["profile_id"]
    )
    assert (await client.get(exact_path)).json()["result"] == first
