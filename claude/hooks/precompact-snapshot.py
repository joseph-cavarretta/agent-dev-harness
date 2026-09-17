#!/usr/bin/env python3
"""PreCompact hook: snapshot uncommitted work state before context is summarized.

Writes a snapshot to ~/.claude/last-session-state.md and injects additionalContext
so the compactor includes in-progress work in its summary. On auto-compact, also
emits a systemMessage to alert the user.
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

data = json.load(sys.stdin)
compact_type = data.get("type", "unknown")

timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
snapshot_lines = [
    f"# Pre-Compaction Snapshot — {timestamp}",
    f"Triggered by: {compact_type} compact",
    "",
    "## Uncommitted changes across ~/dev/",
    "",
]

dev_path = Path.home() / "dev"
found_changes = False

try:
    for repo_dir in sorted(dev_path.iterdir()):
        if not (repo_dir / ".git").is_dir():
            continue
        try:
            result = subprocess.run(
                ["git", "status", "--short", "--branch"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=3,
            )
            all_lines = result.stdout.strip().splitlines()
            branch = "unknown"
            for line in all_lines:
                if line.startswith("## "):
                    # "## main...origin/main" or "## HEAD (no branch)" or "## main"
                    branch_part = line[3:].split("...")[0].strip()
                    branch = branch_part if branch_part else "unknown"
                    break

            status_lines = [l for l in all_lines if not l.startswith("## ") and l]

            # Also check for worktrees
            wt_result = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=3,
            )
            worktrees = [
                l[len("worktree "):] for l in wt_result.stdout.splitlines()
                if l.startswith("worktree ") and str(repo_dir) not in l
            ]

            if status_lines:
                wt_note = f", {len(worktrees)} extra worktree(s)" if worktrees else ""
                snapshot_lines.append(
                    f"**{repo_dir.name}** (branch: `{branch}`{wt_note}): {len(status_lines)} changed file(s)"
                )
                snapshot_lines.extend(f"  {l}" for l in status_lines)
                if worktrees:
                    snapshot_lines.append(f"  worktrees: {', '.join(worktrees)}")
                snapshot_lines.append("")
                found_changes = True
        except Exception:
            pass
except Exception:
    pass

if not found_changes:
    snapshot_lines.append("No uncommitted changes found in ~/dev/.")
    snapshot_lines.append("")

snapshot_path = Path.home() / ".claude" / "last-session-state.md"
snapshot_path.write_text("\n".join(snapshot_lines))

# additionalContext guides the compactor — include in-progress work so it
# survives the summary and is available to the next session
context = (
    "## Critical: preserve in compaction summary\n\n"
    "The following in-progress work was detected at compaction time. "
    "The compaction summary MUST include this so the next session can resume correctly.\n\n"
    + "\n".join(snapshot_lines[3:])
)

output = {
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
