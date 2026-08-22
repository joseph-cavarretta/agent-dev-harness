import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest
from antigravity_mcp.config import Settings
from antigravity_mcp.models import ExecutionResult, Usage, Verification
from antigravity_mcp.server import create_server

TOOL_NAMES = (
    "delegate_task",
    "delegate_vault_document",
    "delegate_code_draft",
    "refine_delegation",
    "delegation_stats",
)


class DummyRunner:
    def __init__(self, should_succeed: bool = True, structured: Optional[Dict[str, Any]] = None) -> None:
        self.should_succeed = should_succeed
        self.structured = structured
        self.last_prompt = ""
        self.last_target_file: Optional[str] = None
        self.last_working_directory: Optional[str] = None
        self.last_additional_dirs: Optional[List[str]] = None
        self.last_conversation_id: Optional[str] = None
        self.last_model: Optional[str] = None
        self.last_effort: Optional[str] = None
        self.last_output_schema: Optional[Dict[str, Any]] = None
        self.calls = 0

    def run_prompt(
        self,
        prompt: str,
        working_directory: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        additional_dirs: Optional[List[str]] = None,
        target_file: Optional[str] = None,
        conversation_id: Optional[str] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        self.calls += 1
        self.last_prompt = prompt
        self.last_target_file = target_file
        self.last_working_directory = working_directory
        self.last_additional_dirs = additional_dirs
        self.last_conversation_id = conversation_id
        self.last_model = model
        self.last_effort = effort
        self.last_output_schema = output_schema

        if not self.should_succeed:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="agy exploded",
                exit_code=1,
                command=["agy"],
                target_file=target_file,
                conversation_id="conv-42",
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
            structured_output=self.structured,
        )


class DummyVerifier:
    def __init__(self, passed: bool = True) -> None:
        self.passed = passed
        self.last_command: Optional[str] = None
        self.last_directory: Optional[str] = None

    def run(self, command: str, working_directory: str, timeout_seconds: int) -> Verification:
        self.last_command = command
        self.last_directory = working_directory
        return Verification(
            command=command,
            passed=self.passed,
            exit_code=0 if self.passed else 1,
            output="1 passed" if self.passed else "1 failed: AssertionError",
        )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        vault_path=tmp_path / "vault",
        vault_templates_path=tmp_path / "vault" / "_templates",
        dev_path=tmp_path / "dev",
        log_path=tmp_path / "delegations.jsonl",
    )


def _server(tmp_path: Path, runner=None, verifier=None):
    return create_server(
        settings=_settings(tmp_path),
        runner=runner or DummyRunner(),
        verifier=verifier or DummyVerifier(),
    )


def _tool(server, name: str):
    tool = server._tool_manager.get_tool(name)
    assert tool is not None
    return tool


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_every_parameter_has_a_description(tmp_path: Path, name: str) -> None:
    """The whole point of the schema: Claude must see what each argument means."""
    properties = _tool(_server(tmp_path), name).parameters["properties"]
    assert properties, f"{name} exposes no parameters"
    missing = [key for key, spec in properties.items() if not spec.get("description")]
    assert not missing, f"{name} parameters missing descriptions: {missing}"


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_every_tool_has_a_docstring(tmp_path: Path, name: str) -> None:
    assert _tool(_server(tmp_path), name).description


def test_effort_is_an_enum_in_the_schema(tmp_path: Path) -> None:
    spec = _tool(_server(tmp_path), "delegate_task").parameters["properties"]["effort"]
    assert "low" in json.dumps(spec) and "high" in json.dumps(spec)


def test_delegate_task_passes_through_workspace_and_overrides(tmp_path: Path) -> None:
    runner = DummyRunner()
    server = _server(tmp_path, runner)

    result = _tool(server, "delegate_task").fn(
        instruction="Summarize the deploy logs",
        working_directory=str(tmp_path),
        additional_dirs=[str(tmp_path / "extra")],
        conversation_id="warm-1",
        model="gemini-3.1-pro",
        effort="low",
    )

    assert runner.last_prompt == "Summarize the deploy logs"
    assert runner.last_additional_dirs == [str(tmp_path / "extra")]
    assert runner.last_conversation_id == "warm-1"
    assert runner.last_model == "gemini-3.1-pro"
    assert runner.last_effort == "low"
    assert "1,000 in / 200 out (800 cached)" in result


def test_output_schema_is_forwarded_and_rendered(tmp_path: Path) -> None:
    schema = {"type": "object", "properties": {"severity": {"type": "string"}}}
    runner = DummyRunner(structured={"severity": "high"})
    server = _server(tmp_path, runner)

    result = _tool(server, "delegate_task").fn(
        instruction="Classify this incident", output_schema=schema
    )

    assert runner.last_output_schema == schema
    assert "Structured output (schema-validated)" in result
    assert '"severity": "high"' in result
    assert "facts in it are not verified" in result


def test_code_draft_runs_the_verify_loop_and_checks_independently(tmp_path: Path) -> None:
    runner = DummyRunner()
    verifier = DummyVerifier(passed=True)
    server = _server(tmp_path, runner, verifier)

    result = _tool(server, "delegate_code_draft").fn(
        target_file=str(tmp_path / "worker.py"),
        task_description="Retry with exponential backoff",
        verify_command="uv run pytest -q",
        verify_directory=str(tmp_path),
    )

    assert "Close the loop yourself" in runner.last_prompt
    assert "uv run pytest -q" in runner.last_prompt
    assert "Never edit or weaken the check" in runner.last_prompt
    assert verifier.last_command == "uv run pytest -q"
    assert verifier.last_directory == str(tmp_path)
    assert "PASSED" in result
    assert "Verification (run by this server, not agy)" in result
    assert "read the diff for design, not for bugs" in result


def test_verification_overrides_agy_claiming_success(tmp_path: Path) -> None:
    """agy has claimed success on work that did not pass. The check decides."""
    server = _server(tmp_path, DummyRunner(should_succeed=True), DummyVerifier(passed=False))

    result = _tool(server, "delegate_code_draft").fn(
        target_file=str(tmp_path / "worker.py"),
        task_description="Anything",
        verify_command="pytest -q",
    )

    assert "FAILED" in result
    assert "agy claimed success. The check disagrees" in result


def test_verification_rescues_agy_reporting_a_false_failure(tmp_path: Path) -> None:
    """Observed for real: agy returned status ERROR on a run whose check passed."""
    server = _server(tmp_path, DummyRunner(should_succeed=False), DummyVerifier(passed=True))

    result = _tool(server, "delegate_code_draft").fn(
        target_file=str(tmp_path / "worker.py"),
        task_description="Anything",
        verify_command="pytest -q",
    )

    assert "PASSED" in result
    assert "agy's status is unreliable" in result


def test_code_draft_warns_when_nothing_proves_it_works(tmp_path: Path) -> None:
    server = _server(tmp_path)

    result = _tool(server, "delegate_code_draft").fn(
        target_file=str(tmp_path / "worker.py"), task_description="Anything"
    )

    assert "No verify_command given" in result
    assert "nothing proves this works" in result


def test_code_draft_sends_paths_not_file_contents(tmp_path: Path) -> None:
    context = tmp_path / "existing.py"
    context.write_text("SECRET_MARKER = 'do not inline me'\n", encoding="utf-8")
    runner = DummyRunner()
    server = _server(tmp_path, runner)

    _tool(server, "delegate_code_draft").fn(
        target_file=str(tmp_path / "src" / "worker.py"),
        task_description="Implement a retry loop",
        context_files=[str(context)],
    )

    assert str(context) in runner.last_prompt
    assert "SECRET_MARKER" not in runner.last_prompt


def test_code_draft_reports_missing_context_files(tmp_path: Path) -> None:
    server = _server(tmp_path)
    result = _tool(server, "delegate_code_draft").fn(
        target_file=str(tmp_path / "worker.py"),
        task_description="Anything",
        context_files=[str(tmp_path / "ghost.py")],
    )
    assert "not found and skipped" in result and "ghost.py" in result


def test_vault_document_infers_template_and_includes_schema(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.vault_templates_path.mkdir(parents=True)
    (settings.vault_templates_path / "investigation.md").write_text(
        "# {{title}}\n## Root Cause\n", encoding="utf-8"
    )
    settings.vault_path.joinpath("schema.md").write_text("# Vault Schema\n", encoding="utf-8")
    runner = DummyRunner()
    server = create_server(settings=settings, runner=runner, verifier=DummyVerifier())

    result = _tool(server, "delegate_vault_document").fn(
        relative_path="investigations/prod-incident.md",
        topic="Gateway pool exhaustion",
        source_context="504s on /v1/ingest",
    )

    assert "Root Cause" in runner.last_prompt
    assert "Vault Schema" in runner.last_prompt
    assert "Template: investigation.md" in result


def test_vault_document_reports_when_agy_did_not_write_the_file(tmp_path: Path) -> None:
    """Observed for real: agy said the page was created when it was not."""
    server = _server(tmp_path)
    result = _tool(server, "delegate_vault_document").fn(
        relative_path="wiki/repos/ghost.md", topic="Ghost", source_context="notes"
    )
    assert "agy did not create the file" in result


def test_vault_document_cleans_up_directory_it_created_on_failure(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    server = create_server(
        settings=settings, runner=DummyRunner(should_succeed=False), verifier=DummyVerifier()
    )

    _tool(server, "delegate_vault_document").fn(
        relative_path="investigations/nested/incident.md", topic="Anything", source_context="notes"
    )

    assert not (settings.vault_path / "investigations" / "nested").exists()


def test_failure_response_omits_the_review_checklist(tmp_path: Path) -> None:
    server = _server(tmp_path, DummyRunner(should_succeed=False))
    result = _tool(server, "delegate_task").fn(instruction="Do a thing")

    assert "FAILED" in result
    assert "agy exploded" in result
    assert "Review before calling this done" not in result
    assert "refine_delegation rather than starting over" in result


def test_refine_delegation_resumes_and_can_verify(tmp_path: Path) -> None:
    runner = DummyRunner()
    verifier = DummyVerifier(passed=True)
    server = _server(tmp_path, runner, verifier)

    result = _tool(server, "refine_delegation").fn(
        conversation_id="conv-42",
        feedback="The summary buries the root cause.",
        working_directory=str(tmp_path),
        verify_command="pytest -q",
    )

    assert runner.last_conversation_id == "conv-42"
    assert "buries the root cause" in runner.last_prompt
    assert "Close the loop yourself" in runner.last_prompt
    assert verifier.last_command == "pytest -q"
    assert "PASSED" in result


def test_delegation_log_records_every_call(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    server = create_server(settings=settings, runner=DummyRunner(), verifier=DummyVerifier())

    _tool(server, "delegate_task").fn(instruction="one")
    _tool(server, "delegate_code_draft").fn(
        target_file=str(tmp_path / "w.py"), task_description="two", verify_command="pytest -q"
    )
    _tool(server, "refine_delegation").fn(conversation_id="conv-42", feedback="three")

    rows = [
        json.loads(line)
        for line in settings.log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [r["tool"] for r in rows] == [
        "delegate_task",
        "delegate_code_draft",
        "refine_delegation",
    ]
    assert rows[1]["verified"] is True
    assert rows[2]["refine_of"] == "conv-42"
    assert rows[0]["input_tokens"] == 1000


def test_delegation_stats_reports_correction_rate_and_disagreement(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    server = create_server(settings=settings, runner=DummyRunner(), verifier=DummyVerifier())

    _tool(server, "delegate_task").fn(instruction="one")
    _tool(server, "refine_delegation").fn(conversation_id="conv-42", feedback="fix it")

    result = _tool(server, "delegation_stats").fn()
    assert "First attempts: 1" in result
    assert "corrections sent back: 1" in result
    assert "Correction rate: 100%" in result


def test_delegation_stats_handles_no_log(tmp_path: Path) -> None:
    result = _tool(_server(tmp_path), "delegation_stats").fn()
    assert "No delegation log yet" in result
