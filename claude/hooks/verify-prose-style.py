#!/usr/bin/env python3
# posttooluse hook: checks markdown documentation style with vale-lint.
# runs after any write or edit tool call on markdown files.
# injects additionalcontext if style issues or errors are detected.
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# directories and files skipped by default (templates, logs, agent prompts, envs)
SKIP_PATTERN = re.compile(
    r"(^|/)(?:"
    r"(?:\.obsidian|_templates|\.local|\.claude|\.cursor|\.worktrees|worktrees|\.venv|venv|node_modules|raw|archive|\.github)/"
    r"|(?:INDEX|log|CHANGELOG|CLAUDE(?:\.[A-Za-z0-9_-]+)?|AGENTS|SKILL)\.md$"
    r")"
)
WORKTREE_ROOT_PATTERN = re.compile(r"^.*?/(?:\.(?:cursor|claude)/)?\.?worktrees/[^/]+/")


def _is_skipped_path(path_str: str) -> bool:
    """Check whether a file path should be skipped after stripping any worktree root."""
    normalized = WORKTREE_ROOT_PATTERN.sub("/", path_str)
    return bool(SKIP_PATTERN.search(normalized))


def _extract_file_path(data: dict[str, object]) -> str | None:
    """Extract edited file path from hook payload."""
    raw = data.get("file_path") or data.get("path")
    if isinstance(raw, str) and raw:
        return raw

    tool_input = data.get("tool_input")
    if isinstance(tool_input, dict):
        raw_tool = (
            tool_input.get("path")
            or tool_input.get("file_path")
            or tool_input.get("TargetFile")
        )
        if isinstance(raw_tool, str) and raw_tool:
            return raw_tool

    return None


def main() -> None:
    """Run vale-lint on edited markdown file and report findings."""
    try:
        data: dict[str, object] = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        sys.exit(0)

    path_str = _extract_file_path(data)
    if not path_str or not path_str.endswith((".md", ".mdx")):
        sys.exit(0)

    file_path = Path(path_str).resolve()
    if not file_path.is_file() or _is_skipped_path(str(file_path)):
        sys.exit(0)

    vale_lint_bin = shutil.which("vale-lint")
    if not vale_lint_bin:
        sys.exit(0)

    # run prose linter on the modified markdown file
    result = subprocess.run(  # noqa: S603  # trusted local linter binary
        [vale_lint_bin, str(file_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        output = (result.stdout + "\n" + result.stderr).strip()
        warning_msg = (
            f"Prose linter (`vale-lint`) found style issues in `{file_path.name}`:\n"
            f"{output}\n\n"
            "Please revise the text following Google Technical Writing style "
            "(second person or imperative, sentence-case headings, no editorial 'we')."
        )
        print(
            json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": warning_msg,
                },
            })
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
