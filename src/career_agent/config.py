from decimal import Decimal
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from career_agent.interview.policy import InterviewPolicy
from career_agent.models.timeouts import TimeoutSeconds
from career_agent.runtime.contracts import Identifier


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CAREER_AGENT_", env_file=".env", extra="ignore")
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://career:career_local_only@127.0.0.1:55432/career_agent"
    )
    typst_bin: str = "typst"
    compile_timeout_seconds: float = Field(default=15, gt=0, le=60)
    font_dir: Path = Path("~/.cache/career-agent/fonts/noto-sans-cjk-sc-2.004")
    data_dir: Path = Path("~/.local/share/career-agent")

    openai_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("OPENAI_API_KEY", "openai_api_key")
    )
    tavily_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("TAVILY_API_KEY", "tavily_api_key")
    )
    live_enabled: bool = False
    interview_policy: InterviewPolicy = Field(default_factory=InterviewPolicy)
    research_fail_fast: bool = False
    cheap_model: str = "gpt-6-luna"
    strong_model: str = "gpt-6.1-sol"
    premium_model: str = "gpt-6-astra"
    premium_enabled: bool = False
    model_timeout_seconds: TimeoutSeconds = 60
    model_task_timeout_seconds: dict[Identifier, TimeoutSeconds] = Field(
        default_factory=lambda: {"interview_preparation": 120.0}
    )
    model_retry_limit: int = Field(default=1, ge=0, le=2)
    schema_repair_limit: int = Field(default=1, ge=0, le=1)
    company_research_ttl_hours: int = Field(default=168, ge=1, le=720)
    search_timeout_seconds: float = Field(default=15, gt=0, le=30)
    search_cost_per_call: Decimal = Field(default=Decimal("0.008"), ge=0)
    cheap_input_price: Decimal = Field(default=Decimal("0.10"), ge=0)
    cheap_cached_price: Decimal = Field(default=Decimal("0.01"), ge=0)
    cheap_output_price: Decimal = Field(default=Decimal("0.50"), ge=0)
    strong_input_price: Decimal = Field(default=Decimal("2"), ge=0)
    strong_cached_price: Decimal = Field(default=Decimal("0.10"), ge=0)
    strong_output_price: Decimal = Field(default=Decimal("10"), ge=0)
    pricing_version: str = "openai-standard-2026-10-10"
    max_run_cost: Decimal = Field(default=Decimal("1"), gt=0, le=5)

    @field_validator("data_dir", "font_dir")
    @classmethod
    def expand_data_dir(cls, value: Path) -> Path:
        return value.expanduser().resolve()
