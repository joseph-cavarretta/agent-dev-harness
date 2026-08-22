from pathlib import Path
from typing import List, Optional
import pytest
from antigravity_mcp.config import Settings
from antigravity_mcp.models import ExecutionResult, Usage
from antigravity_mcp.protocols import AgyRunnerProtocol
from antigravity_mcp.server import create_server

TOOL_NAMES = ("delegate_task", "delegate_vault_document", "delegate_code_draft", "refine_delegation")


class DummyRunner(AgyRunnerProtocol):
    def __init__(self, should_succeed: bool = True) -> None:
        self.should_succeed = should_succeed
        self.last_prompt = ""
        self.last_target_file: Optional[str] = None
        self.last_working_directory: Optional[str] = None
        self.last_additional_dirs: Optional[List[str]] = None
        self.last_conversation_id: Optional[str] = None

    def run_prompt(
        self,
        prompt: str,
        working_directory: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        additional_dirs: Optional[List[str]] = None,
        target_file: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> ExecutionResult:
        self.last_prompt = prompt
        self.last_target_file = target_file
        self.last_working_directory = working_directory
        self.last_additional_dirs = additional_dirs
        self.last_conversation_id = conversation_id

        if not self.should_succeed:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="agy exploded",
                exit_code=1,
                command=["agy"],
                target_file=target_file,
            )
        return ExecutionResult(
            success=True,
            stdout="Draft complete.",
            stderr="",
            exit_code=0,
            command=["agy"],
            target_file=target_file,
            conversation_id="conv-42",
            duration_seconds=9.0,
            usage=Usage(input_tokens=1000, output_tokens=200, cache_read_tokens=800, total_tokens=1200),
        )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        vault_path=tmp_path / "vault",
        vault_templates_path=tmp_path / "vault" / "_templates",
        dev_path=tmp_path / "dev",
    )


def _tool(server, name: str):
    tool = server._tool_manager.get_tool(name)
    assert tool is not None
    return tool


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_every_parameter_has_a_description(tmp_path: Path, name: str) -> None:
    """The whole point of the schema: Claude must see what each argument means."""
    server = create_server(settings=_settings(tmp_path), runner=DummyRunner())
    properties = _tool(server, name).parameters["properties"]

    assert properties, f"{name} exposes no parameters"
    missing = [key for key, spec in properties.items() if not spec.get("description")]
    assert not missing, f"{name} parameters missing descriptions: {missing}"


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_every_tool_documents_when_not_to_use_it(tmp_path: Path, name: str) -> None:
    server = create_server(settings=_settings(tmp_path), runner=DummyRunner())
    assert _tool(server, name).description


def test_delegate_task_passes_through_workspace(tmp_path: Path) -> None:
    runner = DummyRunner()
    server = create_server(settings=_settings(tmp_path), runner=runner)

    result = _tool(server, "delegate_task").fn(
        instruction="Summarize the deploy logs",
        working_directory=str(tmp_path),
        additional_dirs=[str(tmp_path / "extra")],
    )

    assert runner.last_prompt == "Summarize the deploy logs"
    assert runner.last_working_directory == str(tmp_path)
    assert runner.last_additional_dirs == [str(tmp_path / "extra")]
    assert "1,000 in / 200 out (800 cached)" in result
    assert "conv-42" in result


def test_code_draft_sends_paths_not_file_contents(tmp_path: Path) -> None:
    context = tmp_path / "existing.py"
    context.write_text("SECRET_MARKER = 'do not inline me'\n", encoding="utf-8")
    runner = DummyRunner()
    server = create_server(settings=_settings(tmp_path), runner=runner)

    _tool(server, "delegate_code_draft").fn(
        target_file=str(tmp_path / "src" / "worker.py"),
        task_description="Implement a retry loop with exponential backoff",
        context_files=[str(context)],
    )

    assert str(context) in runner.last_prompt
    assert "SECRET_MARKER" not in runner.last_prompt
    assert "Pydantic models" in runner.last_prompt


def test_code_draft_reports_missing_context_files(tmp_path: Path) -> None:
    runner = DummyRunner()
    server = create_server(settings=_settings(tmp_path), runner=runner)

    result = _tool(server, "delegate_code_draft").fn(
        target_file=str(tmp_path / "worker.py"),
        task_description="Anything",
        context_files=[str(tmp_path / "ghost.py")],
    )

    assert "not found and skipped" in result
    assert "ghost.py" in result


def test_vault_document_infers_template_and_includes_schema(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.vault_templates_path.mkdir(parents=True)
    (settings.vault_templates_path / "investigation.md").write_text(
        "# {{title}}\n## Root Cause\n", encoding="utf-8"
    )
    settings.vault_path.joinpath("schema.md").write_text(
        "# Vault Schema\nLog format: YYYY-MM-DD | ACTION | page\n", encoding="utf-8"
    )
    runner = DummyRunner()
    server = create_server(settings=settings, runner=runner)

    result = _tool(server, "delegate_vault_document").fn(
        relative_path="investigations/prod-incident.md",
        topic="Gateway pool exhaustion",
        source_context="504s on /v1/ingest",
    )

    assert "Root Cause" in runner.last_prompt
    assert "Vault Schema" in runner.last_prompt
    assert "Gateway pool exhaustion" in runner.last_prompt
    assert "Template: investigation.md" in result
    assert "Vault schema included" in result


def test_vault_document_uses_wiki_template_for_wiki_paths(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.vault_templates_path.mkdir(parents=True)
    (settings.vault_templates_path / "wiki.md").write_text(
        "# {{title}}\n**Last updated:** {{date}}\n", encoding="utf-8"
    )
    runner = DummyRunner()
    server = create_server(settings=settings, runner=runner)

    _tool(server, "delegate_vault_document").fn(
        relative_path="wiki/repos/gateway-service.md",
        topic="Gateway service",
        source_context="notes",
    )

    assert "Last updated" in runner.last_prompt


def test_vault_document_cleans_up_directory_it_created_on_failure(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    server = create_server(settings=settings, runner=DummyRunner(should_succeed=False))

    _tool(server, "delegate_vault_document").fn(
        relative_path="investigations/nested/incident.md",
        topic="Anything",
        source_context="notes",
    )

    assert not (settings.vault_path / "investigations" / "nested").exists()


def test_failure_response_omits_the_review_checklist(tmp_path: Path) -> None:
    server = create_server(settings=_settings(tmp_path), runner=DummyRunner(should_succeed=False))

    result = _tool(server, "delegate_task").fn(instruction="Do a thing")

    assert "FAILED" in result
    assert "agy exploded" in result
    assert "Review before calling this done" not in result
    assert "do not retry the same delegation blind" in result


def test_refine_delegation_resumes_the_conversation(tmp_path: Path) -> None:
    runner = DummyRunner()
    server = create_server(settings=_settings(tmp_path), runner=runner)

    result = _tool(server, "refine_delegation").fn(
        conversation_id="conv-42",
        feedback="The summary section buries the root cause. Lead with it.",
        working_directory=str(tmp_path),
        target_file=str(tmp_path / "note.md"),
    )

    assert runner.last_conversation_id == "conv-42"
    assert "buries the root cause" in runner.last_prompt
    assert "Re-read only the parts you asked it to change." in result
