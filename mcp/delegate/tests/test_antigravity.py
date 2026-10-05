import json
import subprocess
from unittest.mock import MagicMock, patch

from delegate_mcp.config import Settings
from delegate_mcp.infra.antigravity import AntigravityRunner, parse_json_output
from delegate_mcp.models import WorkerRun

WORKER_JSON = {
    "conversation_id": "abc-123",
    "status": "SUCCESS",
    "response": "Draft written.\n",
    "duration_seconds": 12.5,
    "usage": {
        "input_tokens": 48891,
        "output_tokens": 509,
        "thinking_tokens": 331,
        "cache_read_tokens": 14941,
        "total_tokens": 49400,
    },
}


def test_runner_constructs_correct_cli_command() -> None:
    settings = Settings(
        default_model="gemini-3.7-flash",
        default_effort="high",
        dangerously_skip_permissions=True,
    )
    runner = AntigravityRunner(settings)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(WORKER_JSON), stderr=""
        )
        result = runner.run(
            WorkerRun(
                prompt="Test prompt",
                working_directory="/srv/project",
                additional_dirs=["/srv/extra-dir"],
            )
        )

    assert result.command == [
        str(settings.worker_bin_path),
        "--print",
        "Test prompt",
        "--model",
        "gemini-3.7-flash",
        "--effort",
        "high",
        "--output-format",
        "json",
        "--print-timeout",
        "300s",
        "--dangerously-skip-permissions",
        "--add-dir",
        "/srv/extra-dir",
    ]


def test_runner_parses_json_payload() -> None:
    runner = AntigravityRunner(Settings())

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(WORKER_JSON), stderr=""
        )
        result = runner.run(WorkerRun(prompt="Draft something"))

    assert result.success is True
    assert result.stdout == "Draft written.\n"
    assert result.conversation_id == "abc-123"
    # measured locally, not taken from the CLI's unreliable duration_seconds
    assert result.duration_seconds is not None
    assert result.duration_seconds != 12.5
    assert result.usage is not None
    assert result.usage.input_tokens == 48891
    assert result.usage.cache_read_tokens == 14941


def test_runner_resumes_conversation() -> None:
    runner = AntigravityRunner(Settings())

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(WORKER_JSON), stderr=""
        )
        result = runner.run(
            WorkerRun(prompt="Fix the header", conversation_id="abc-123")
        )

    assert "--conversation" in result.command
    assert result.command[result.command.index("--conversation") + 1] == "abc-123"


def test_runner_treats_failed_status_as_failure() -> None:
    runner = AntigravityRunner(Settings())
    payload = {**WORKER_JSON, "status": "FAILED", "error": "tool loop exceeded"}

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(payload), stderr=""
        )
        result = runner.run(WorkerRun(prompt="Draft something"))

    assert result.success is False
    assert "tool loop exceeded" in result.stderr


def test_runner_falls_back_when_output_is_not_json() -> None:
    runner = AntigravityRunner(Settings())

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="plain text reply", stderr=""
        )
        result = runner.run(WorkerRun(prompt="Draft something"))

    assert result.success is True
    assert result.stdout == "plain text reply"
    assert result.usage is None


def test_subprocess_timeout_exceeds_print_timeout() -> None:
    settings = Settings(timeout_grace_seconds=30)
    runner = AntigravityRunner(settings)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        runner.run(WorkerRun(prompt="Test prompt", timeout_seconds=120))

    assert mock_run.call_args.kwargs["timeout"] == 150
    cmd = mock_run.call_args.args[0]
    assert cmd[cmd.index("--print-timeout") + 1] == "120s"


def test_runner_handles_timeout() -> None:
    runner = AntigravityRunner(Settings())

    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="agy", timeout=5, output=b"partial"),
    ):
        result = runner.run(WorkerRun(prompt="Long running prompt", timeout_seconds=5))

    assert result.success is False
    assert result.exit_code == -1
    assert "did not exit within 35s" in result.stderr
    assert result.stdout == "partial"


def test_runner_handles_missing_binary() -> None:
    runner = AntigravityRunner(Settings())

    with patch("subprocess.run", side_effect=OSError("No such file")):
        result = runner.run(WorkerRun(prompt="Anything"))

    assert result.success is False
    assert "Could not run" in result.stderr


def test_parse_json_output_skips_leading_log_lines() -> None:
    stdout = "warming up\n" + json.dumps(WORKER_JSON)
    parsed = parse_json_output(stdout)
    assert parsed is not None
    assert parsed["conversation_id"] == "abc-123"


def test_parse_json_output_returns_none_for_empty() -> None:
    assert parse_json_output("   ") is None


def test_output_schema_and_overrides_reach_the_cli() -> None:
    runner = AntigravityRunner(Settings())
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}}

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(WORKER_JSON), stderr=""
        )
        result = runner.run(
            WorkerRun(
                prompt="Classify",
                model="gemini-3.1-pro",
                effort="low",
                output_schema=schema,
            )
        )

    cmd = result.command
    assert cmd[cmd.index("--model") + 1] == "gemini-3.1-pro"
    assert cmd[cmd.index("--effort") + 1] == "low"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == schema


def test_structured_output_is_parsed_separately_from_prose() -> None:
    runner = AntigravityRunner(Settings())
    payload = {
        **WORKER_JSON,
        "response": "chatty prose with toolAction noise",
        "structured_output": {"severity": "high"},
    }

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(payload), stderr=""
        )
        result = runner.run(WorkerRun(prompt="Classify"))

    assert result.structured_output == {"severity": "high"}
    assert "toolAction" in result.stdout


def test_invalid_effort_fails_before_spawning_worker() -> None:
    runner = AntigravityRunner(Settings())

    with patch("subprocess.run") as mock_run:
        result = runner.run(WorkerRun(prompt="anything", effort="ludicrous"))

    mock_run.assert_not_called()
    assert result.success is False
    assert "effort must be one of" in result.stderr
