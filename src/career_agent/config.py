from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CAREER_AGENT_", env_file=".env", extra="ignore")
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://career:career_local_only@127.0.0.1:55432/career_agent"
    )
    data_dir: Path = Path("~/.local/share/career-agent")

    @field_validator("data_dir")
    @classmethod
    def expand_data_dir(cls, value: Path) -> Path:
        return value.expanduser().resolve()
