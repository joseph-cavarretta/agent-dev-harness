#!/usr/bin/env python3
"""PreToolUse / beforeShellExecution guard: lint PR descriptions with Vale.

Intercepts `gh pr create`, `gh pr edit`, and `gh api` pull-request body updates,
runs the extracted Markdown body through `vale-lint --stdin`, and blocks the
command with actionable violations if any prose rules fail.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PR_CMD_RE = re.compile(r"\bgh\s+pr\s+(?:create|edit)\b")
GH_API_RE = re.compile(r"\bgh\s+api\b")
PULLS_TARGET_RE = re.compile(r"(?:^|[\s/'\"])pulls(?:/\d+)?(?=$|[\s'\"])")

HEREDOC_BODY_RE = re.compile(
    r"(?:--body(?:=|\s+)|-b(?:=|\s+)|(?:-f|-F|--field|--raw-field)(?:=|\s+)body=)"
    r"\s*\"?\$\(\s*cat\s+<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?\s*\n"
    r"(.*?)\n[ \t]*\1\s*\)\"?",
    re.DOTALL,
)
DOUBLE_QUOTED_BODY_RE = re.compile(
    r'(?:--body(?:=|\s+)|-b(?:=|\s+)|(?:-f|--field|--raw-field)(?:=|\s+)body=)"((?:[^"\\]|\\.)*)"',
    re.DOTALL,
)
SINGLE_QUOTED_BODY_RE = re.compile(
    r"(?:--body(?:=|\s+)|-b(?:=|\s+)|(?:-f|--field|--raw-field)(?:=|\s+)body=)'([^']*)'",
    re.DOTALL,
)
PR_BODY_FILE_RE = re.compile(
    r"(?:--body-file|-F)(?:=|\s+)(?:\"([^\"]+)\"|'([^']+)'|(\S+))"
)
API_BODY_FILE_RE = re.compile(
    r"(?:-F|--field)(?:=|\s+)body=@(?:\"([^\"]+)\"|'([^']+)'|(\S+))"
)
CD_PREFIX_RE = re.compile(r"\bcd\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))")


def _extract_command(payload: dict[str, object]) -> tuple[str, bool]:
    """Return the shell command and whether the caller is Claude Code."""
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        cmd = tool_input.get("command") or tool_input.get("CommandLine") or ""
        return (cmd if isinstance(cmd, str) else ""), True
    cmd = payload.get("command") or ""
    return (cmd if isinstance(cmd, str) else ""), False


def _is_pr_body_command(command: str) -> bool:
    """Return whether the command creates or updates a GitHub PR description."""
    if PR_CMD_RE.search(command):
        return True
    return bool(GH_API_RE.search(command) and PULLS_TARGET_RE.search(command))


def _resolve_base_dirs(command: str, payload: dict[str, object]) -> list[Path]:
    """Return candidate directories for resolving relative `--body-file` paths."""
    dirs: list[Path] = []
    cd_match = CD_PREFIX_RE.search(command)
    if cd_match:
        raw_cd = cd_match.group(1) or cd_match.group(2) or cd_match.group(3)
        if raw_cd:
            dirs.append(Path(raw_cd).expanduser())
    roots = payload.get("workspace_roots")
    if isinstance(roots, list):
        for root in roots:
            if isinstance(root, str) and root:
                dirs.append(Path(root))
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        dirs.append(Path(cwd))
    dirs.append(Path.cwd())
    return dirs


def _read_body_file(raw_path: str, base_dirs: list[Path]) -> str | None:
    """Read a PR body file from candidate base directories, skipping stdin `-`."""
    if not raw_path or raw_path == "-":
        return None
    candidate = Path(raw_path).expanduser()
    paths = [candidate] if candidate.is_absolute() else [d / candidate for d in base_dirs]
    for path in paths:
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                return None
    return None


def _unescape_double_quoted(raw: str) -> str:
    """Unescape common double-quoted shell escapes for Vale linting."""
    return (
        raw.replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\\\", "\\")
    )


def _extract_body(command: str, payload: dict[str, object]) -> str | None:
    """Extract PR description Markdown from inline flags, heredocs, or files."""
    heredoc = HEREDOC_BODY_RE.search(command)
    if heredoc:
        return heredoc.group(2)

    if PR_CMD_RE.search(command):
        pr_file = PR_BODY_FILE_RE.search(command)
        if pr_file:
            raw_path = pr_file.group(1) or pr_file.group(2) or pr_file.group(3) or ""
            return _read_body_file(raw_path, _resolve_base_dirs(command, payload))
    else:
        api_file = API_BODY_FILE_RE.search(command)
        if api_file:
            raw_path = api_file.group(1) or api_file.group(2) or api_file.group(3) or ""
            return _read_body_file(raw_path, _resolve_base_dirs(command, payload))

    single = SINGLE_QUOTED_BODY_RE.search(command)
    if single:
        return single.group(1)

    double = DOUBLE_QUOTED_BODY_RE.search(command)
    if double:
        return _unescape_double_quoted(double.group(1))

    return None


def _find_vale_lint() -> str | None:
    """Locate the `vale-lint` executable on PATH or standard harness locations."""
    found = shutil.which("vale-lint")
    if found:
        return found
    for candidate in (
        Path.home() / ".local/bin/vale-lint",
        Path(__file__).resolve().parents[2] / "prose-styleguide/vale-lint",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def _allow(*, is_claude: bool) -> None:
    """Allow the command cleanly for the active harness."""
    if not is_claude:
        print(json.dumps({"permission": "allow"}))
    sys.exit(0)


def _deny(reason: str, *, is_claude: bool) -> None:
    """Block the command with Vale diagnostics for either Claude Code or Cursor."""
    print(
        json.dumps(
            {
                "permission": "deny",
                "user_message": reason,
                "agent_message": reason,
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                },
            }
        )
    )
    sys.exit(0 if is_claude else 2)


def main() -> None:
    """Lint extracted PR description prose and deny on Vale findings."""
    try:
        payload: dict[str, object] = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        sys.exit(0)

    command, is_claude = _extract_command(payload)
    if not command or not _is_pr_body_command(command):
        _allow(is_claude=is_claude)

    body = _extract_body(command, payload)
    if not body or not body.strip():
        _allow(is_claude=is_claude)

    vale_lint_bin = _find_vale_lint()
    if not vale_lint_bin:
        _allow(is_claude=is_claude)

    result = subprocess.run(  # noqa: S603  # trusted local vale-lint binary
        [vale_lint_bin, "--stdin"],
        input=body,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        output = (result.stdout + "\n" + result.stderr).strip()
        reason = (
            "Prose linter (`vale-lint`) found style issues in the PR description.\n"
            "Follow Google Technical Writing style (second person or imperative, "
            "sentence-case headings, no bold lead-in bullets, no editorial 'we') "
            "and revise before running `gh`:\n\n"
            f"{output}"
        )
        _deny(reason, is_claude=is_claude)

    _allow(is_claude=is_claude)


if __name__ == "__main__":
    main()
