from pathlib import Path
from antigravity_mcp.verify import MAX_OUTPUT_CHARS, ShellVerifier


def test_passing_command() -> None:
    result = ShellVerifier().run("echo hello", working_directory="/tmp", timeout_seconds=30)
    assert result.passed is True
    assert result.exit_code == 0
    assert "hello" in result.output


def test_failing_command_captures_output(tmp_path: Path) -> None:
    result = ShellVerifier().run(
        "echo 'boom' >&2; exit 3", working_directory=str(tmp_path), timeout_seconds=30
    )
    assert result.passed is False
    assert result.exit_code == 3
    assert "boom" in result.output


def test_command_runs_in_the_given_directory(tmp_path: Path) -> None:
    (tmp_path / "marker.txt").write_text("x", encoding="utf-8")
    result = ShellVerifier().run("ls", working_directory=str(tmp_path), timeout_seconds=30)
    assert result.passed is True
    assert "marker.txt" in result.output


def test_timeout_is_reported_as_a_failure(tmp_path: Path) -> None:
    result = ShellVerifier().run("sleep 5", working_directory=str(tmp_path), timeout_seconds=1)
    assert result.passed is False
    assert "did not finish within 1s" in result.output


def test_bad_directory_is_reported_not_raised() -> None:
    result = ShellVerifier().run("echo hi", working_directory="/nope/nope", timeout_seconds=10)
    assert result.passed is False
    assert "could not run verify command" in result.output


def test_long_output_is_truncated_from_the_front(tmp_path: Path) -> None:
    result = ShellVerifier().run(
        f"python3 -c \"print('x' * {MAX_OUTPUT_CHARS * 2})\"",
        working_directory=str(tmp_path),
        timeout_seconds=30,
    )
    assert result.passed is True
    assert result.output.startswith("...(truncated)...")
    assert len(result.output) < MAX_OUTPUT_CHARS + 100
