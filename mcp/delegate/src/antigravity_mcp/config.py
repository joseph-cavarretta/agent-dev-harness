from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    agy_bin_path: Path = Field(default_factory=lambda: Path.home() / ".local" / "bin" / "agy")
    default_model: str = "gemini-3.7-flash"
    default_effort: str = "high"
    default_timeout_seconds: int = 300
    timeout_grace_seconds: int = 30
    verify_timeout_seconds: int = 300
    max_verify_rounds: int = 4
    vault_path: Path = Field(default_factory=lambda: Path.home() / ".vault")
    vault_templates_path: Path = Field(default_factory=lambda: Path.home() / ".vault" / "_templates")
    dev_path: Path = Field(default_factory=lambda: Path.home() / "dev")
    dangerously_skip_permissions: bool = True
    log_path: Path = Field(
        default_factory=lambda: Path.home() / ".claude" / "antigravity-delegations.jsonl"
    )

    model_config = SettingsConfigDict(
        env_prefix="ANTIGRAVITY_MCP_",
        case_sensitive=False,
    )

    @property
    def vault_schema_path(self) -> Path:
        return self.vault_path / "schema.md"
