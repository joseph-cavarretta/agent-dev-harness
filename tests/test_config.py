from pathlib import Path
from antigravity_mcp.config import Settings


def test_default_settings() -> None:
    settings = Settings()
    assert settings.default_model == "gemini-3.7-flash"
    assert settings.default_effort == "high"
    assert settings.default_timeout_seconds == 300
    assert settings.timeout_grace_seconds == 30
    assert settings.dangerously_skip_permissions is True
    assert isinstance(settings.agy_bin_path, Path)
    assert isinstance(settings.vault_path, Path)


def test_vault_schema_path_follows_vault_path(tmp_path: Path) -> None:
    settings = Settings(vault_path=tmp_path)
    assert settings.vault_schema_path == tmp_path / "schema.md"
