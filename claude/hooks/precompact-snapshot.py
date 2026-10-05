#!/usr/bin/env python3
"""PreCompact hook: snapshot uncommitted work state before context is summarized.

Writes a snapshot to ~/.claude/last-session-state.md and injects additionalContext
so the compactor includes in-progress work in its summary. On auto-compact, also
emits a systemMessage to alert the user.
"""

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DEV_PATH = Path.home() / "dev"
SNAPSHOT_PATH = Path.home() / ".claude" / "last-session-state.md"
GIT_TIMEOUT_SECONDS = 3
# A repo whose git call fails or times out is left out rather than failing the hook.
_GIT_ERRORS = (OSError, ValueError, subprocess.SubprocessError)


def _git(git: str, repo_dir: Path, *args: str) -> list[str]:
    """Output lines of a git command run in repo_dir."""
    result = subprocess.run(  # noqa: S603  # fixed git arguments, no user input
        [git, *args],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
        check=False,
    )
    return result.stdout.strip().splitlines()


def repo_section(git: str, repo_dir: Path) -> list[str]:
    """Snapshot lines for one repo, or nothing when its working tree is clean."""
    status = _git(git, repo_dir, "status", "--short", "--branch")
    branch = "unknown"
    for line in status:
        if line.startswith("## "):
            # Header forms: `## main...origin/main`, `## HEAD (no branch)`, `## main`
            branch = line[3:].split("...")[0].strip() or "unknown"
            break
    changed = [line for line in status if line and not line.startswith("## ")]
    if not changed:
        return []

    worktrees = [
        line[len("worktree ") :]
        for line in _git(git, repo_dir, "worktree", "list", "--porcelain")
        if line.startswith("worktree ") and str(repo_dir) not in line
    ]
    wt_note = f", {len(worktrees)} extra worktree(s)" if worktrees else ""
    section = [
        f"**{repo_dir.name}** (branch: `{branch}`{wt_note}): "
        f"{len(changed)} changed file(s)",
        *(f"  {line}" for line in changed),
    ]
    if worktrees:
        section.append(f"  worktrees: {', '.join(worktrees)}")
    section.append("")
    return section


def changes_across_dev() -> list[str]:
    """Snapshot lines for every repo under ~/dev with uncommitted changes."""
    git = shutil.which("git")
    if git is None:
        return []
    try:
        repo_dirs = sorted(d for d in DEV_PATH.iterdir() if (d / ".git").is_dir())
    except OSError:
        return []
    lines: list[str] = []
    for repo_dir in repo_dirs:
        try:
            lines.extend(repo_section(git, repo_dir))
        except _GIT_ERRORS:
            continue
    return lines


def main() -> None:
    """Write the snapshot file and print the PreCompact hook output."""
    compact_type = json.load(sys.stdin).get("type", "unknown")
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    changes = changes_across_dev() or [
        "No uncommitted changes found in ~/dev/.",
        "",
    ]
    snapshot_lines = [
        f"# Pre-Compaction Snapshot — {timestamp}",
        f"Triggered by: {compact_type} compact",
        "",
        "## Uncommitted changes across ~/dev/",
        "",
        *changes,
    ]
    SNAPSHOT_PATH.write_text("\n".join(snapshot_lines))

    # additionalContext guides the compactor — include in-progress work so it
    # survives the summary and is available to the next session
    context = (
        "## Critical: preserve in compaction summary\n\n"
        "The following in-progress work was detected at compaction time. "
        "The compaction summary MUST include this so the next session can resume "
        "correctly.\n\n" + "\n".join(snapshot_lines[3:])
    )
    output: dict[str, object] = {
        "hookSpecificOutput": {
            "hookEventName": "PreCompact",
            "additionalContext": context,
        }
    }
    if compact_type == "auto":
        output["systemMessage"] = (
            f"Auto-compact triggered at {timestamp}. "
            "Snapshot saved to ~/.claude/last-session-state.md — "
            "read it at session start if context seems thin."
        )
    print(json.dumps(output))


if __name__ == "__main__":
    main()
