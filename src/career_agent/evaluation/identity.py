"""Stable hashes and a frozen candidate manifest; pricing never governs business reuse."""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from career_agent.application.compatibility import execution_versions
from career_agent.config import Settings
from career_agent.evaluation.contracts import CandidateConfig
from career_agent.models.gateway import ModelGateway
from career_agent.models.prompts import application_prompts
from career_agent.preparation.providers import POLICY, registry
from career_agent.preparation.research import SearchToolMetadata
from career_agent.runtime.registry import REGISTRY


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()


def code_identity() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    files = sorted(root.rglob("*.py")) + sorted(root.rglob("*.typ"))
    code_hash = digest(
        {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    )
    try:
        code_revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        code_revision = "unavailable"
    return {"code_revision": code_revision, "code_hash": code_hash}


def candidate_config(settings: Settings, gateway: ModelGateway | None = None) -> CandidateConfig:
    identity = code_identity()
    prompts = gateway.prompts if gateway else application_prompts()
    policy = gateway.policy if gateway else POLICY
    search = SearchToolMetadata()
    value = CandidateConfig(
        **identity,
        prompts={
            task: {
                **spec.metadata,
                "instruction": spec.instruction,
                "input_contract": spec.input_contract,
                "executable_input": spec.executable_input.model_dump(mode="json")
                if spec.executable_input
                else None,
                "output_schema": spec.output_schema.model_json_schema(),
            }
            for task, spec in prompts.specs.items()
        },
        schemas={
            **{task: spec.output_schema_version for task, spec in prompts.specs.items()},
            **{f"action:{key}:input": spec.args_schema_version for key, spec in REGISTRY.items()},
            **{
                f"action:{key}:output": spec.result_schema_version for key, spec in REGISTRY.items()
            },
            f"tool:{search.tool_name}:input": search.input_schema_version,
            f"tool:{search.tool_name}:output": search.output_schema_version,
        },
        components={
            **{key: spec.version for key, spec in REGISTRY.items()},
            search.tool_name: search.tool_version,
            "runtime": "agent-runtime-v1",
        },
        execution_settings={
            key: value
            for key, value in settings.model_dump(mode="json").items()
            if key
            not in {"database_url", "data_dir", "font_dir", "openai_api_key", "tavily_api_key"}
        },
        model_policy={
            "version": policy.version,
            "task_tiers": {k: v.value for k, v in policy.task_tiers.items()},
            "candidates": [
                x.model_dump(mode="json")
                for x in (gateway.registry if gateway else registry(settings, False))
            ],
        },
        validators={**execution_versions("resume_tailoring"), "evaluator": "eval-check-v1"},
    )
    value.config_hash = digest(value.model_dump(mode="json", exclude={"config_hash"}))
    return value
