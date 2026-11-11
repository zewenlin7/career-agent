"""Historical readability is independent of eligibility for a new execution."""

from dataclasses import dataclass

from career_agent.resume.fonts import FONT_POLICY_VERSION
from career_agent.resume.schemas import (
    COMPILER_VERSION,
    POLICY_VERSION,
    SCHEMA_VERSION,
    TEMPLATE_VERSION,
)

POLICY = "artifact-compatibility-v1"


def model_execution_versions(task: str) -> dict[str, str]:
    """Freeze the actual task contract, not an unrelated Resume execution contract."""
    from career_agent.models.prompts import application_prompts

    spec = application_prompts().resolve(task)
    target = {"company_research_synthesis": "company_research"}.get(task, task)
    business = (
        execution_versions(target)
        if target
        in {
            "company_research",
            "fit_analysis",
            "resume_tailoring",
            "greeting_generation",
            "interview_preparation",
        }
        else {}
    )
    return {**business, **spec.metadata, "task": task}


def execution_versions(target: str) -> dict[str, str]:
    versions = {
        "source": "profile-job-snapshot-v1",
        "schema": "preparation-output-v1",
        "validator": "preparation-guardrails-v1",
        "grounding": "verified-grounding-v1",
    }
    tasks = {
        "company_research": "company_research_synthesis",
        "fit_analysis": "fit_analysis",
        "resume_tailoring": "resume_tailoring",
        "greeting_generation": "greeting_generation",
        "interview_preparation": "interview_preparation",
    }
    if target in tasks:
        from career_agent.preparation.contracts import TaskType
        from career_agent.preparation.prompts import PROMPTS

        task = TaskType(tasks[target])
        key = {"company_research": "research_prompt", "fit_analysis": "fit_prompt"}.get(
            target, "generation_prompt"
        )
        versions[key] = PROMPTS[task].prompt_hash
    if target == "resume_tailoring":
        versions.update(
            tailoring_layout="structured-entry-budget-v2",
            resume_schema=SCHEMA_VERSION,
            template=TEMPLATE_VERSION,
            layout=POLICY_VERSION,
            compiler=COMPILER_VERSION,
            font=FONT_POLICY_VERSION,
            render="resume-render-wrapper-v5",
            pdf="resume-validation-v4",
        )
    return versions


@dataclass(frozen=True)
class CompatibilityDecision:
    historical_readable: bool
    reusable_for_current_execution: bool
    reason_code: str
    policy_version: str = POLICY


def compatible(stored: dict[str, str] | None, current: dict[str, str]) -> CompatibilityDecision:
    if stored is None or not current.keys() <= stored.keys():
        return CompatibilityDecision(True, False, "compatibility_metadata_missing")
    if any(stored[key] != value for key, value in current.items()):
        return CompatibilityDecision(True, False, "execution_version_incompatible")
    return CompatibilityDecision(True, True, "execution_compatible")
