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


def execution_versions(target: str) -> dict[str, str]:
    versions = {
        "source": "profile-job-snapshot-v1",
        "schema": "preparation-output-v1",
        "validator": "preparation-guardrails-v1",
        "grounding": "verified-grounding-v1",
    }
    if target == "resume_tailoring":
        versions.update(
            resume_schema=SCHEMA_VERSION,
            template=TEMPLATE_VERSION,
            layout=POLICY_VERSION,
            compiler=COMPILER_VERSION,
            font=FONT_POLICY_VERSION,
            render="resume-render-wrapper-v1",
            pdf="resume-validation-v1",
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
