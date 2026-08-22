from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    agy_bin_path: Path = Path("/Users/joseph/.local/bin/agy")
    default_model: str = "gemini-3.7-flash"
    default_effort: str = "high"
    default_timeout_seconds: int = 300
    timeout_grace_seconds: int = 30
    vault_path: Path = Path("/Users/joseph/.vault")
    vault_templates_path: Path = Path("/Users/joseph/.vault/_templates")
    dev_path: Path = Path("/Users/joseph/dev")
    dangerously_skip_permissions: bool = True

    model_config = SettingsConfigDict(
        env_prefix="ANTIGRAVITY_MCP_",
        case_sensitive=False,
    )

    @property
    def vault_schema_path(self) -> Path:
        return self.vault_path / "schema.md"
