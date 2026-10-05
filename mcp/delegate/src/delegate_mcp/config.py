from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server settings, read from DELEGATE_MCP_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="DELEGATE_MCP_", extra="forbid")

    worker_bin_path: Path = Field(
        default_factory=lambda: Path.home() / ".local" / "bin" / "agy",
        description="Worker agent CLI binary.",
    )
    default_model: str = Field(
        default="gemini-3.7-flash",
        description="Worker model used when a call does not name one.",
    )
    default_effort: str = Field(
        default="high",
        description="Reasoning effort used when a call does not set one.",
    )
    default_timeout_seconds: int = Field(
        default=300, description="Worker wall-clock budget per call, in seconds."
    )
    timeout_grace_seconds: int = Field(
        default=30,
        description=(
            "Extra seconds the subprocess gets past the worker's own timeout, so the "
            "worker times out first and its error message is kept."
        ),
    )
    verify_timeout_seconds: int = Field(
        default=300, description="Budget for one run of a verify command, in seconds."
    )
    max_verify_rounds: int = Field(
        default=4,
        description="Most times a code draft is re-checked and sent back to the worker.",
    )
    vault_path: Path = Field(
        default_factory=lambda: Path.home() / ".vault",
        description="Knowledge-base root; the vault tool is only offered when it exists.",
    )
    vault_templates_path: Path = Field(
        default_factory=lambda: Path.home() / ".vault" / "_templates",
        description="Directory of vault page templates.",
    )
    dev_path: Path = Field(
        default_factory=lambda: Path.home() / "dev",
        description="Default working directory for the worker.",
    )
    dangerously_skip_permissions: bool = Field(
        default=True,
        description="Run the worker with its permission prompts auto-approved.",
    )
    log_path: Path = Field(
        default_factory=lambda: Path.home() / ".claude" / "delegations.jsonl",
        description="JSONL log of every delegation, read by delegation_stats.",
    )

    @property
    def vault_schema_path(self) -> Path:
        """The vault's schema.md, which governs page layout and conventions."""
        return self.vault_path / "schema.md"
