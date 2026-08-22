import json
import subprocess
from unittest.mock import MagicMock, patch
from antigravity_mcp.config import Settings
from antigravity_mcp.runner import AgyRunner, _parse_agy_json

AGY_JSON = {
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
    runner = AgyRunner(settings)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(AGY_JSON), stderr="")
        result = runner.run_prompt(
            prompt="Test prompt",
            working_directory="/Users/joseph/dev",
            additional_dirs=["/Users/joseph/.vault"],
        )

    assert result.command == [
        str(settings.agy_bin_path),
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
        "/Users/joseph/.vault",
    ]


def test_runner_parses_json_payload() -> None:
    runner = AgyRunner(Settings())

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(AGY_JSON), stderr="")
        result = runner.run_prompt("Draft something")

    assert result.success is True
    assert result.stdout == "Draft written.\n"
    assert result.conversation_id == "abc-123"
    # measured locally, not taken from agy's unreliable duration_seconds
    assert result.duration_seconds is not None and result.duration_seconds != 12.5
    assert result.usage is not None
    assert result.usage.input_tokens == 48891
    assert result.usage.cache_read_tokens == 14941


def test_runner_resumes_conversation() -> None:
    runner = AgyRunner(Settings())

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(AGY_JSON), stderr="")
        result = runner.run_prompt("Fix the header", conversation_id="abc-123")

    assert "--conversation" in result.command
    assert result.command[result.command.index("--conversation") + 1] == "abc-123"


def test_runner_treats_failed_status_as_failure() -> None:
    runner = AgyRunner(Settings())
    payload = {**AGY_JSON, "status": "FAILED", "error": "tool loop exceeded"}

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(payload), stderr="")
        result = runner.run_prompt("Draft something")

    assert result.success is False
    assert "tool loop exceeded" in result.stderr


def test_runner_falls_back_when_output_is_not_json() -> None:
    runner = AgyRunner(Settings())

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="plain text reply", stderr="")
        result = runner.run_prompt("Draft something")

    assert result.success is True
    assert result.stdout == "plain text reply"
    assert result.usage is None


def test_subprocess_timeout_exceeds_print_timeout() -> None:
    settings = Settings(timeout_grace_seconds=30)
    runner = AgyRunner(settings)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        runner.run_prompt("Test prompt", timeout_seconds=120)

    assert mock_run.call_args.kwargs["timeout"] == 150
    cmd = mock_run.call_args.args[0]
    assert cmd[cmd.index("--print-timeout") + 1] == "120s"


def test_runner_handles_timeout() -> None:
    runner = AgyRunner(Settings())

    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="agy", timeout=5, output=b"partial"),
    ):
        result = runner.run_prompt("Long running prompt", timeout_seconds=5)

    assert result.success is False
    assert result.exit_code == -1
    assert "did not exit within 35s" in result.stderr
    assert result.stdout == "partial"


def test_runner_handles_missing_binary() -> None:
    runner = AgyRunner(Settings())

    with patch("subprocess.run", side_effect=OSError("No such file")):
        result = runner.run_prompt("Anything")

    assert result.success is False
    assert "Could not run" in result.stderr


def test_parse_agy_json_skips_leading_log_lines() -> None:
    stdout = "warming up\n" + json.dumps(AGY_JSON)
    parsed = _parse_agy_json(stdout)
    assert parsed is not None
    assert parsed["conversation_id"] == "abc-123"


def test_parse_agy_json_returns_none_for_empty() -> None:
    assert _parse_agy_json("   ") is None
