#!/usr/bin/env python3
"""PostToolUse on Edit|Write: format and auto-fix the edited Python file with ruff.

Fixable issues cost the model nothing: they are fixed on disk right after the edit.
Only violations ruff can't fix are sent back to Claude, as additionalContext (exit
code 2 is not honored for PostToolUse). Runs only in repos that configure ruff, using
that repo's config. Any failure of the hook itself exits 0 silently.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

MAX_REPORTED = 20
TIMEOUT_S = 20
RUFF_CONFIGS = ("ruff.toml", ".ruff.toml")
# A concise-format violation: `<path>:<line>:<col>: <code> <message>`. The path is
# relative to the config directory, so match the shape, not the path.
VIOLATION = re.compile(r"^.+?:(\d+:\d+: .+)$")


def is_python(path: Path) -> bool:
    """A .py/.pyi file, or an extensionless script with a python or `uv run` shebang."""
    if path.suffix in (".py", ".pyi"):
        return True
    if path.suffix:
        return False
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            first = f.readline()
    except OSError:
        return False
    return first.startswith("#!") and ("python" in first or "uv run" in first)


def ruff_config_dir(path: Path) -> Path | None:
    """Nearest directory configuring ruff, searching up to the repo root."""
    for directory in path.parents:
        if any((directory / name).is_file() for name in RUFF_CONFIGS):
            return directory
        pyproject = directory / "pyproject.toml"
        if pyproject.is_file() and "[tool.ruff" in pyproject.read_text(
            errors="replace"
        ):
            return directory
        if (directory / ".git").exists():
            return None
    return None


def ruff_command() -> list[str] | None:
    """The ruff command: on PATH, else through uvx, else None."""
    if shutil.which("ruff"):
        return ["ruff"]
    if shutil.which("uvx"):
        return ["uvx", "ruff"]
    return None


def fix(path: Path, config_dir: Path, ruff: list[str]) -> list[str]:
    """Format and safe-fix `path`; return the violations that remain."""

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        # The command is ruff plus the edited file's path, not untrusted input.
        return subprocess.run(  # noqa: S603
            [*ruff, *args],
            cwd=config_dir,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            check=False,
        )

    # --force-exclude: honor the repo's excludes even though the path is explicit.
    run("format", "--force-exclude", str(path))
    result = run(
        "check", "--fix", "--force-exclude", "--output-format", "concise", str(path)
    )
    if result.returncode == 0:
        return []
    return [
        f"{path.name}:{m[1]}"
        for line in result.stdout.splitlines()
        if (m := VIOLATION.match(line))
    ]


def report(path: Path, violations: list[str]) -> str:
    """The message Claude sees: the remaining violations, capped."""
    shown = violations[:MAX_REPORTED]
    more = len(violations) - len(shown)
    lines = [
        f"ruff auto-fixed and formatted {path}; {len(violations)} issue(s) need a manual fix:",
        *shown,
    ]
    if more:
        lines.append(f"... and {more} more (run ruff check on the file)")
    return "\n".join(lines)


def main() -> int:
    """Fix the edited file and report what is left; never fail the tool call."""
    try:
        event = json.load(sys.stdin)
        raw = (event.get("tool_input") or {}).get("file_path")
        if not raw:
            return 0
        path = Path(raw).resolve()
        if not path.is_file() or not is_python(path):
            return 0
        config_dir = ruff_config_dir(path)
        ruff = ruff_command()
        if config_dir is None or ruff is None:
            return 0
        violations = fix(path, config_dir, ruff)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0
    if violations:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": report(path, violations),
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
