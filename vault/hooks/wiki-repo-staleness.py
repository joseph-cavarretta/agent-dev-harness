#!/usr/bin/env python3
"""PostToolUse hook: warns when a stale wiki/repos/ page has recent git commits.

Fires after any Read of ~/.vault/wiki/repos/*.md. Extracts the Last updated
date, skips if <60 days old, then checks ~/dev/<repo-name>/ for commits since
that date. Injects an additionalContext warning if genuine drift is detected.
"""
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

data = json.load(sys.stdin)
file_path = data.get("tool_input", {}).get("file_path", "")

if "/wiki/repos/" not in file_path or not file_path.endswith(".md"):
    sys.exit(0)

try:
    content = Path(file_path).read_text()
except Exception:
    sys.exit(0)

m = re.search(r'\*\*Last updated:\*\*\s*(\d{4}-\d{2}-\d{2})', content)
if not m:
    sys.exit(0)

try:
    last_updated = date.fromisoformat(m.group(1))
except ValueError:
    sys.exit(0)

age_days = (date.today() - last_updated).days
if age_days <= 60:
    sys.exit(0)

repo_name = Path(file_path).stem
repo_path = Path.home() / "dev" / repo_name

if not repo_path.is_dir():
    sys.exit(0)

try:
    result = subprocess.run(
        ["git", "log", f"--after={last_updated.isoformat()}", "--oneline"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=5,
    )
    commits = [ln for ln in result.stdout.strip().splitlines() if ln]
except Exception:
    sys.exit(0)

if not commits:
    sys.exit(0)

n = len(commits)
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": (
            f"⚠ wiki/repos/{repo_name}.md is stale (last updated {last_updated}, "
            f"{age_days} days ago). ~/dev/{repo_name}/ has "
            f"{n} commit{'s' if n != 1 else ''} since then — "
            f"treat this page as potentially out of date and consider regenerating it."
        ),
    }
}))
