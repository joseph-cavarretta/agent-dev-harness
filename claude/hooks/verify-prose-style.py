#!/usr/bin/env python3
# PostToolUse hook: lint an edited Markdown file with vale-lint and hand any findings
# back to Claude as additionalContext.
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Directories and files skipped by default (templates, logs, agent prompts, envs).
SKIP_PATTERN = re.compile(
    r"(^|/)(?:"
    r"(?:\.obsidian|_templates|\.local|\.claude|\.worktrees|worktrees|\.venv|venv|node_modules|raw|archive|\.github)/"
    r"|(?:INDEX|log|CHANGELOG|CLAUDE(?:\.[A-Za-z0-9_-]+)?|AGENTS|SKILL)\.md$"
    r")"
)
WORKTREE_ROOT_PATTERN = re.compile(r"^.*?/(?:\.claude/)?\.?worktrees/[^/]+/")


def _is_skipped_path(path_str: str) -> bool:
    """Check whether a file path should be skipped after stripping any worktree root."""
    normalized = WORKTREE_ROOT_PATTERN.sub("/", path_str)
    return bool(SKIP_PATTERN.search(normalized))


def _extract_file_path(data: dict[str, object]) -> str | None:
    """Return the edited file path from a Claude Code Edit or Write payload."""
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path")
    return raw if isinstance(raw, str) and raw else None


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
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": warning_msg,
                    },
                }
            )
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
