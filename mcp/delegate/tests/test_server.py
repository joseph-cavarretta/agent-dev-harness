import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, Tool

from delegate_mcp.app.context import AppContext
from delegate_mcp.config import Settings
from delegate_mcp.entrypoints.server import create_server
from delegate_mcp.models import ExecutionResult, Usage, Verification, WorkerRun

TOOL_NAMES = (
    "delegate_task",
    "delegate_vault_document",
    "delegate_code_draft",
    "refine_delegation",
    "delegation_stats",
)


class DummyRunner:
    def __init__(
        self, should_succeed: bool = True, structured: dict[str, Any] | None = None
    ) -> None:
        self.should_succeed = should_succeed
        self.structured = structured
        self.last_prompt = ""
        self.last_target_file: str | None = None
        self.last_working_directory: str | None = None
        self.last_additional_dirs: list[str] | None = None
        self.last_conversation_id: str | None = None
        self.last_model: str | None = None
        self.last_effort: str | None = None
        self.last_output_schema: dict[str, Any] | None = None
        self.calls = 0

    def run(self, job: WorkerRun) -> ExecutionResult:
        self.calls += 1
        self.last_prompt = job.prompt
        self.last_target_file = job.target_file
        self.last_working_directory = job.working_directory
        self.last_additional_dirs = job.additional_dirs
        self.last_conversation_id = job.conversation_id
        self.last_model = job.model
        self.last_effort = job.effort
        self.last_output_schema = job.output_schema
        target_file = job.target_file

        if not self.should_succeed:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="worker exploded",
                exit_code=1,
                command=["worker"],
                target_file=target_file,
                conversation_id="conv-42",
            )
        return ExecutionResult(
            success=True,
            stdout="Draft complete.",
            stderr="",
            exit_code=0,
            command=["worker"],
            target_file=target_file,
            conversation_id="conv-42",
            duration_seconds=9.0,
            usage=Usage(
                input_tokens=1000,
                output_tokens=200,
                cache_read_tokens=800,
                total_tokens=1200,
            ),
            structured_output=self.structured,
        )


class DummyVerifier:
    def __init__(self, passed: bool = True, sequence: list[bool] | None = None) -> None:
        self.passed = passed
        self.sequence = list(sequence) if sequence else None
        self.calls = 0
        self.commands: list[str] = []
        self.last_command: str | None = None
        self.last_directory: str | None = None

    def run(
        self,
        command: str,
        working_directory: str,
        timeout_seconds: int,  # noqa: ARG002  # matches the verifier protocol
    ) -> Verification:
        self.calls += 1
        self.commands.append(command)
        self.last_command = command
        self.last_directory = working_directory
        if self.sequence:
            ok = self.sequence.pop(0) if self.sequence else self.passed
        else:
            ok = self.passed
        return Verification(
            command=command,
            passed=ok,
            exit_code=0 if ok else 1,
            output="1 passed" if ok else "1 failed: AssertionError: add(2,3)=-1",
        )


def _settings(tmp_path: Path) -> Settings:
    (tmp_path / "vault").mkdir(exist_ok=True)
    return Settings(
        vault_path=tmp_path / "vault",
        vault_templates_path=tmp_path / "vault" / "_templates",
        dev_path=tmp_path / "dev",
        log_path=tmp_path / "delegations.jsonl",
    )


def _server(
    tmp_path: Path,
    runner: DummyRunner | None = None,
    verifier: DummyVerifier | None = None,
) -> MCPServer:
    return _create(
        _settings(tmp_path), runner or DummyRunner(), verifier or DummyVerifier()
    )


def _create(
    settings: Settings, runner: DummyRunner, verifier: DummyVerifier
) -> MCPServer:
    return create_server(AppContext(settings, runner, verifier))


def _tools(server: MCPServer) -> dict[str, Tool]:
    return {tool.name: tool for tool in asyncio.run(server.list_tools())}


def _call(server: MCPServer, name: str, **arguments: object) -> str:
    result = asyncio.run(server.call_tool(name, arguments))
    if not isinstance(result, CallToolResult):
        pytest.fail(f"{name} asked for more input instead of returning a result")
    return "".join(getattr(block, "text", "") for block in result.content)


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_every_parameter_has_a_description(tmp_path: Path, name: str) -> None:
    """The whole point of the schema: Claude must see what each argument means."""
    properties = _tools(_server(tmp_path))[name].input_schema["properties"]
    assert properties, f"{name} exposes no parameters"
    missing = [key for key, spec in properties.items() if not spec.get("description")]
    assert not missing, f"{name} parameters missing descriptions: {missing}"


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_every_tool_has_a_docstring(tmp_path: Path, name: str) -> None:
    assert _tools(_server(tmp_path))[name].description


def test_effort_is_an_enum_in_the_schema(tmp_path: Path) -> None:
    spec = _tools(_server(tmp_path))["delegate_task"].input_schema["properties"][
        "effort"
    ]
    assert "low" in json.dumps(spec)
    assert "high" in json.dumps(spec)


def test_delegate_task_passes_through_workspace_and_overrides(tmp_path: Path) -> None:
    runner = DummyRunner()
    server = _server(tmp_path, runner)

    result = _call(
        server,
        "delegate_task",
        instruction="Summarize the deploy logs",
        working_directory=str(tmp_path),
        additional_dirs=[str(tmp_path / "extra")],
        conversation_id="warm-1",
        model="stronger-model",
        effort="low",
    )

    assert runner.last_prompt == "Summarize the deploy logs"
    assert runner.last_additional_dirs == [str(tmp_path / "extra")]
    assert runner.last_conversation_id == "warm-1"
    assert runner.last_model == "stronger-model"
    assert runner.last_effort == "low"
    assert "1,000 in / 200 out (800 cached)" in result


def test_output_schema_is_forwarded_and_rendered(tmp_path: Path) -> None:
    schema = {"type": "object", "properties": {"severity": {"type": "string"}}}
    runner = DummyRunner(structured={"severity": "high"})
    server = _server(tmp_path, runner)

    result = _call(
        server,
        "delegate_task",
        instruction="Classify this incident",
        output_schema=schema,
    )

    assert runner.last_output_schema == schema
    assert "Structured output (schema-validated)" in result
    assert '"severity": "high"' in result
    assert "facts in it are not verified" in result


def test_code_draft_runs_the_verify_loop_and_checks_independently(
    tmp_path: Path,
) -> None:
    runner = DummyRunner()
    verifier = DummyVerifier(passed=True)
    server = _server(tmp_path, runner, verifier)

    result = _call(
        server,
        "delegate_code_draft",
        target_file=str(tmp_path / "worker.py"),
        task_description="Retry with exponential backoff",
        verify_command="uv run pytest -q",
        verify_directory=str(tmp_path),
    )

    assert "Check your work before handing it back" in runner.last_prompt
    assert "uv run pytest -q" in runner.last_prompt
    assert "Never edit or weaken the check" in runner.last_prompt
    assert verifier.last_command == f"cd {tmp_path} && uv run pytest -q"
    assert verifier.last_directory == str(tmp_path)
    assert "PASSED" in result
    assert "Verification (run by this server, not the worker)" in result
    assert "read the diff for design, not for bugs" in result


def test_verification_overrides_worker_claiming_success(tmp_path: Path) -> None:
    """The worker has claimed success on work that did not pass. The check decides."""
    server = _server(
        tmp_path, DummyRunner(should_succeed=True), DummyVerifier(passed=False)
    )

    result = _call(
        server,
        "delegate_code_draft",
        target_file=str(tmp_path / "worker.py"),
        task_description="Anything",
        verify_command="pytest -q",
    )

    assert "FAILED" in result
    assert "The worker claimed success. The check disagrees" in result


def test_verification_rescues_worker_reporting_a_false_failure(tmp_path: Path) -> None:
    """Observed for real: the worker reported ERROR on a run whose check passed."""
    server = _server(
        tmp_path, DummyRunner(should_succeed=False), DummyVerifier(passed=True)
    )

    result = _call(
        server,
        "delegate_code_draft",
        target_file=str(tmp_path / "worker.py"),
        task_description="Anything",
        verify_command="pytest -q",
    )

    assert "PASSED" in result
    assert "Its status is unreliable" in result


def test_code_draft_warns_when_nothing_proves_it_works(tmp_path: Path) -> None:
    server = _server(tmp_path)

    result = _call(
        server,
        "delegate_code_draft",
        target_file=str(tmp_path / "worker.py"),
        task_description="Anything",
    )

    assert "No verify_command given" in result
    assert "nothing proves this works" in result


def test_code_draft_sends_paths_not_file_contents(tmp_path: Path) -> None:
    context = tmp_path / "existing.py"
    context.write_text("SECRET_MARKER = 'do not inline me'\n", encoding="utf-8")
    runner = DummyRunner()
    server = _server(tmp_path, runner)

    _call(
        server,
        "delegate_code_draft",
        target_file=str(tmp_path / "src" / "worker.py"),
        task_description="Implement a retry loop",
        context_files=[str(context)],
    )

    assert str(context) in runner.last_prompt
    assert "SECRET_MARKER" not in runner.last_prompt


def test_code_draft_reports_missing_context_files(tmp_path: Path) -> None:
    server = _server(tmp_path)
    result = _call(
        server,
        "delegate_code_draft",
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
        "# Vault Schema\n", encoding="utf-8"
    )
    runner = DummyRunner()
    server = _create(settings, runner, DummyVerifier())

    result = _call(
        server,
        "delegate_vault_document",
        relative_path="investigations/prod-incident.md",
        topic="Gateway pool exhaustion",
        source_context="504s on /v1/ingest",
    )

    assert "Root Cause" in runner.last_prompt
    assert "Vault Schema" in runner.last_prompt
    assert "Template: investigation.md" in result


def test_vault_document_reports_when_worker_did_not_write_the_file(
    tmp_path: Path,
) -> None:
    """Observed for real: the worker said the page was created when it was not."""
    server = _server(tmp_path)
    result = _call(
        server,
        "delegate_vault_document",
        relative_path="wiki/repos/ghost.md",
        topic="Ghost",
        source_context="notes",
    )
    assert "The worker did not create the file" in result


def test_vault_document_cleans_up_directory_it_created_on_failure(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    server = _create(settings, DummyRunner(should_succeed=False), DummyVerifier())

    _call(
        server,
        "delegate_vault_document",
        relative_path="investigations/nested/incident.md",
        topic="Anything",
        source_context="notes",
    )

    assert not (settings.vault_path / "investigations" / "nested").exists()


def test_failure_response_omits_the_review_checklist(tmp_path: Path) -> None:
    server = _server(tmp_path, DummyRunner(should_succeed=False))
    result = _call(server, "delegate_task", instruction="Do a thing")

    assert "FAILED" in result
    assert "worker exploded" in result
    assert "Review before calling this done" not in result
    assert "refine_delegation rather than starting over" in result


def test_refine_delegation_resumes_and_can_verify(tmp_path: Path) -> None:
    runner = DummyRunner()
    verifier = DummyVerifier(passed=True)
    server = _server(tmp_path, runner, verifier)

    result = _call(
        server,
        "refine_delegation",
        conversation_id="conv-42",
        feedback="The summary buries the root cause.",
        working_directory=str(tmp_path),
        verify_command="pytest -q",
    )

    assert runner.last_conversation_id == "conv-42"
    assert "buries the root cause" in runner.last_prompt
    assert "Check your work before handing it back" in runner.last_prompt
    assert verifier.last_command == f"cd {tmp_path} && pytest -q"
    assert "PASSED" in result


def test_delegation_log_records_every_call(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    server = _create(settings, DummyRunner(), DummyVerifier())

    _call(server, "delegate_task", instruction="one")
    _call(
        server,
        "delegate_code_draft",
        target_file=str(tmp_path / "w.py"),
        task_description="two",
        verify_command="pytest -q",
    )
    _call(server, "refine_delegation", conversation_id="conv-42", feedback="three")

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


def test_delegation_stats_reports_correction_rate_and_disagreement(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    server = _create(settings, DummyRunner(), DummyVerifier())

    _call(server, "delegate_task", instruction="one")
    _call(server, "refine_delegation", conversation_id="conv-42", feedback="fix it")

    result = _call(server, "delegation_stats")
    assert "First attempts: 1" in result
    assert "corrections sent back: 1" in result
    assert "Correction rate: 100%" in result


def test_delegation_stats_handles_no_log(tmp_path: Path) -> None:
    result = _call(_server(tmp_path), "delegation_stats")
    assert "No delegation log yet" in result


def test_verify_command_always_carries_an_explicit_cd(tmp_path: Path) -> None:
    """The worker's shell may start in a scratch dir; without cd the check is wrong."""
    verifier = DummyVerifier(passed=True)
    runner = DummyRunner()
    server = _server(tmp_path, runner, verifier)

    _call(
        server,
        "delegate_code_draft",
        target_file=str(tmp_path / "worker.py"),
        task_description="Anything",
        verify_command="pytest -q",
        verify_directory=str(tmp_path),
    )

    assert verifier.last_command == f"cd {tmp_path} && pytest -q"
    assert f"cd {tmp_path} && pytest -q" in runner.last_prompt


def test_server_retries_with_the_real_failure_until_it_passes(tmp_path: Path) -> None:
    """The loop is driven here, not by the worker: fail, feed the output back, pass."""
    verifier = DummyVerifier(sequence=[False, False, True])
    runner = DummyRunner()
    server = _server(tmp_path, runner, verifier)

    result = _call(
        server,
        "delegate_code_draft",
        target_file=str(tmp_path / "worker.py"),
        task_description="Sum two numbers",
        verify_command="pytest -q",
        verify_directory=str(tmp_path),
    )

    assert verifier.calls == 3
    assert runner.calls == 3
    assert "AssertionError: add(2,3)=-1" in runner.last_prompt
    assert "captured by the caller running" in runner.last_prompt
    assert runner.last_conversation_id == "conv-42"
    assert "Verify rounds: 3" in result
    assert "PASSED" in result


def test_server_gives_up_after_max_rounds(tmp_path: Path) -> None:
    settings = _settings(tmp_path).model_copy(update={"max_verify_rounds": 2})
    verifier = DummyVerifier(passed=False)
    runner = DummyRunner()
    server = _create(settings, runner, verifier)

    result = _call(
        server,
        "delegate_code_draft",
        target_file=str(tmp_path / "worker.py"),
        task_description="Anything",
        verify_command="pytest -q",
    )

    assert verifier.calls == 2
    assert runner.calls == 2
    assert "gave up after 2" in result
    assert "FAILED" in result
    assert "AssertionError" in result


def test_no_retry_loop_when_no_verify_command(tmp_path: Path) -> None:
    verifier = DummyVerifier()
    runner = DummyRunner()
    server = _server(tmp_path, runner, verifier)

    _call(
        server,
        "delegate_code_draft",
        target_file=str(tmp_path / "worker.py"),
        task_description="Anything",
    )

    assert verifier.calls == 0
    assert runner.calls == 1


def test_verify_rounds_are_logged(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    server = _create(settings, DummyRunner(), DummyVerifier(sequence=[False, True]))

    _call(
        server,
        "delegate_code_draft",
        target_file=str(tmp_path / "worker.py"),
        task_description="Anything",
        verify_command="pytest -q",
    )

    row = json.loads(settings.log_path.read_text(encoding="utf-8").splitlines()[0])
    assert row["verify_rounds"] == 2
    assert row["verified"] is True


def test_vault_tool_is_not_offered_without_a_vault(tmp_path: Path) -> None:
    settings = Settings(
        vault_path=tmp_path / "no-vault",
        dev_path=tmp_path / "dev",
        log_path=tmp_path / "d.jsonl",
    )
    server = _create(settings, DummyRunner(), DummyVerifier())
    names = _tools(server)
    assert "delegate_vault_document" not in names
    assert "delegate_task" in names


def test_delegation_stats_counts_logs_written_before_the_rename(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.log_path.write_text(
        json.dumps(
            {"tool": "delegate_task", "agy_reported_success": True, "verified": False}
        )
        + "\n",
        encoding="utf-8",
    )
    server = _create(settings, DummyRunner(), DummyVerifier())
    result = _call(server, "delegation_stats")
    assert "Worker reported success: 1/1" in result
    assert "disagreed with the check 1 time(s)" in result
