"""Explicit deterministic component allowlist reusing production validators."""

from typing import Any
from uuid import UUID

from career_agent.application.compatibility import compatible
from career_agent.domain.rules import FactStatus
from career_agent.interview.contracts import (
    OverallEvaluation,
    QuestionGroupEvaluation,
    SourceSnapshot,
)
from career_agent.interview.validation import validate_evaluation
from career_agent.models.contracts import ModelGatewayError
from career_agent.models.prompts import application_prompts
from career_agent.preparation.contracts import FitOutput, GreetingOutput, RequirementsOutput
from career_agent.preparation.guardrails import validate_extraction, validate_fit, validate_greeting
from career_agent.resume.grounding import FactEvidence, validate_grounding
from career_agent.resume.schemas import InputSnapshot, ResumeDocument
from career_agent.security.model_view import model_view

VERSIONS = {
    name: "v1"
    for name in [
        "artifact_compatibility",
        "model_view",
        "resume_grounding",
        "debrief_evidence",
        "prompt_input",
        "cas",
        "plan_validation",
        "captured_source",
        "research_search",
    ]
}


def deterministic(name: str, data: dict[str, Any]) -> dict[str, Any]:
    if name == "captured_source":
        from career_agent.evaluation.captured import replay_source

        try:
            return {"status": "completed", "source": replay_source(data)}
        except ModelGatewayError as exc:
            return {"status": "completed", "reason_code": exc.code, "valid": False}
    if name == "cas":
        from career_agent.application.services import check_revision

        check_revision(data["actual_revision"], data["expected_revision"])
        return {"status": "completed", "valid": True}
    if name == "plan_validation":
        from career_agent.runtime.agent_contracts import AgentState, PlanProposal
        from career_agent.runtime.plans import validate_plan

        validate_plan(
            PlanProposal.model_validate(data["plan"]),
            AgentState.model_validate(data["state"]),
            set(data["evidence"]),
        )
        return {"status": "completed", "valid": True}
    if name == "artifact_compatibility":
        decision = compatible(data.get("stored"), data["current"])
        return {
            "status": "completed",
            "historical_readable": decision.historical_readable,
            "reusable": decision.reusable_for_current_execution,
            "reason_code": decision.reason_code,
        }
    if name == "model_view":
        return {"status": "completed", "view": model_view(data["value"], name=data.get("name", ""))}
    if name == "prompt_input":
        application_prompts().resolve(data["task_type"]).validate_input(data["inputs"])
        return {"status": "completed", "valid": True}
    if name == "resume_grounding":
        document = ResumeDocument.model_validate(data["document"])
        facts = {
            UUID(f["id"]): FactEvidence(
                UUID(f["id"]), f["revision"], FactStatus(f["status"]), f["statement"]
            )
            for f in data["facts"]
        }
        findings = validate_grounding(
            document,
            InputSnapshot.model_validate(data["snapshot"]),
            {UUID(x) for x in data["members"]},
            facts,
            {UUID(x) for x in data["requirements"]},
        )
        return {
            "status": "completed",
            "valid": not findings,
            "finding_codes": [f.code for f in findings],
        }
    if name == "debrief_evidence":
        source = SourceSnapshot.model_validate(data["source"])
        output = (
            QuestionGroupEvaluation.model_validate(data["output"])
            if data.get("group_ref")
            else OverallEvaluation.model_validate(data["output"])
        )
        validate_evaluation(
            output, source, UUID(data["group_ref"]) if data.get("group_ref") else None
        )
        return {"status": "completed", "valid": True}
    raise ModelGatewayError("case_incompatible")


def validate_task(
    task: str, output: dict[str, Any], inputs: dict[str, Any], source: dict[str, Any]
) -> None:
    blocks = inputs.get("context", inputs)
    facts = {UUID(x["id"]): x for x in blocks.get("facts", [])}
    requirements = {UUID(x["id"]) for x in blocks.get("requirements", [])}
    if task == "job_requirement_extraction":
        validate_extraction(RequirementsOutput.model_validate(output), blocks["job"]["jd_text"])
    elif task == "fit_analysis":
        validate_fit(FitOutput.model_validate(output), requirements, facts)
    elif task == "greeting_generation":
        validate_greeting(GreetingOutput.model_validate(output), requirements, facts)

    elif task == "company_research_synthesis":
        from career_agent.preparation.contracts import ResearchOutput
        from career_agent.preparation.guardrails import validate_research

        validate_research(
            ResearchOutput.model_validate(output), {UUID(x["id"]) for x in blocks["evidence"]}
        )
    elif task == "interview_preparation":
        from career_agent.preparation.contracts import InterviewOutput
        from career_agent.preparation.guardrails import validate_interview

        validate_interview(
            InterviewOutput.model_validate(output),
            requirements,
            set(facts),
            {x["project_ref"] for x in blocks["profile_refs"]["projects"]},
        )
    elif task in {"resume_tailoring", "resume_compression"}:
        from career_agent.preparation.guardrails import validate_compression

        if task == "resume_compression":
            validate_compression(
                ResumeDocument.model_validate(blocks["variant"]),
                ResumeDocument.model_validate(output),
                blocks["protected_fields"],
            )
        grounding = {**source, "document": output}
        if "requirement_ids" in source:
            grounding["requirements"] = source["requirement_ids"]
        check = deterministic("resume_grounding", grounding)
        if not check["valid"]:
            raise ModelGatewayError("grounding_failed")
    elif task in {"interview_group_debrief", "interview_overall_debrief"}:
        deterministic(
            "debrief_evidence",
            {
                "source": source.get("source", source),
                "group_ref": inputs["group"]["group_ref"]
                if task == "interview_group_debrief"
                else None,
                "output": output,
            },
        )
    elif task == "mock_interview_turn_generation":
        from career_agent.interview.contracts import FrozenContext, TurnOutput
        from career_agent.interview.validation import validate_turn

        validate_turn(
            TurnOutput.model_validate(output),
            FrozenContext.model_validate(source.get("context", source)),
            inputs["policy"]["next_kind"],
            UUID(inputs["policy"]["parent"]) if inputs["policy"].get("parent") else None,
        )
    elif task in {"goal_planning", "goal_replanning"}:
        from career_agent.runtime.agent_contracts import AgentState, PlanProposal
        from career_agent.runtime.plans import validate_plan

        validate_plan(
            PlanProposal.model_validate(output),
            AgentState.model_validate(source["state"]),
            set(source["evidence"]),
        )
