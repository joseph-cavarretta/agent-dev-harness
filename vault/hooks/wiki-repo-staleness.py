#!/usr/bin/env python3
"""PostToolUse hook: warns when a stale wiki/repos/ page has recent git commits.

Fires after any Read of ~/.vault/wiki/repos/*.md. Extracts the Last updated
date, skips if <60 days old, then checks ~/dev/<repo-name>/ for commits since
that date. Injects an additionalContext warning if genuine drift is detected.
"""

import json
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

STALE_AFTER_DAYS = 60
GIT_TIMEOUT_SECONDS = 5
LAST_UPDATED_PATTERN = r"\*\*Last updated:\*\*\s*(\d{4}-\d{2}-\d{2})"


def last_updated(page: Path) -> date | None:
    """The page's Last updated date, or None if it is unreadable or has none."""
    try:
        content = page.read_text()
    except (OSError, UnicodeDecodeError):
        return None
    match = re.search(LAST_UPDATED_PATTERN, content)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def commits_since(repo_path: Path, since: date) -> list[str]:
    """One-line commits in repo_path after `since`; empty if git is unavailable."""
    git = shutil.which("git")
    if git is None:
        return []
    try:
        result = subprocess.run(  # noqa: S603  # fixed git arguments, no user input
            [git, "log", f"--after={since.isoformat()}", "--oneline"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    return [line for line in result.stdout.strip().splitlines() if line]


def main() -> None:
    """Print a staleness warning for a stale repo page whose repo has moved on."""
    file_path = json.load(sys.stdin).get("tool_input", {}).get("file_path", "")
    if "/wiki/repos/" not in file_path or not file_path.endswith(".md"):
        return

    updated = last_updated(Path(file_path))
    if updated is None:
        return
    age_days = (datetime.now().astimezone().date() - updated).days
    if age_days <= STALE_AFTER_DAYS:
        return

    repo_name = Path(file_path).stem
    repo_path = Path.home() / "dev" / repo_name
    if not repo_path.is_dir():
        return
    commits = commits_since(repo_path, updated)
    if not commits:
        return

    n = len(commits)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        f"⚠ wiki/repos/{repo_name}.md is stale (last updated "
                        f"{updated}, {age_days} days ago). ~/dev/{repo_name}/ has "
                        f"{n} commit{'s' if n != 1 else ''} since then — "
                        "treat this page as potentially out of date and consider "
                        "regenerating it."
                    ),
                }
            }
        )
    )


if __name__ == "__main__":
    main()
