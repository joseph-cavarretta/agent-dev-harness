#!/usr/bin/env python3
"""SessionStart hook: pre-loads Core Reference wiki pages into context.

Reads the Core Reference pages listed below and injects them as additionalContext
so they land in the prompt prefix on every session, maximizing cache hits for the
pages most likely to be needed.

Customize CORE_PAGES with your own vault's 2-4 most-used pages. Missing files are
skipped silently, so it's safe to leave entries pointing at pages you haven't
created yet (or to run this on a machine with no vault at all).
"""
import json
import sys
from pathlib import Path

# (path, label) — the handful of pages worth loading into every session.
CORE_PAGES = [
    (Path.home() / ".vault/INDEX.md", "Vault Index"),
    # (Path.home() / ".vault/wiki/systems/<your-core-system>.md", "<Your Core System>"),
    # (Path.home() / ".vault/wiki/repos/<your-core-repo>.md", "<Your Core Repo>"),
]

sections = []
for path, label in CORE_PAGES:
    try:
        content = path.read_text()
        sections.append(f"### {label}\n\n{content.strip()}")
    except Exception:
        pass

if not sections:
    sys.exit(0)

combined = "# Core Reference (pre-loaded)\n\n" + "\n\n---\n\n".join(sections)
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": combined,
    }
}))
