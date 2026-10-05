#!/usr/bin/env python3
"""SessionStart hook: pre-loads Core Reference wiki pages into context.

Reads the Core Reference pages listed below and injects them as additionalContext
so they land in the prompt prefix on every session, maximizing cache hits for the
pages most likely to be needed.

Customize CORE_PAGES with your own vault's 2-4 most-used pages, as (path, label)
pairs such as (Path.home() / ".vault/wiki/repos/<repo>.md", "<Repo>"). Missing files
are skipped, so it's safe to run this on a machine with no vault at all.
"""

import json
from pathlib import Path

CORE_PAGES = [
    (Path.home() / ".vault/INDEX.md", "Vault Index"),
]


def main() -> None:
    """Print the readable core pages as SessionStart additionalContext."""
    sections = []
    for path, label in CORE_PAGES:
        try:
            content = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue  # Missing or unreadable pages are expected; skip them.
        sections.append(f"### {label}\n\n{content.strip()}")
    if not sections:
        return

    combined = "# Core Reference (pre-loaded)\n\n" + "\n\n---\n\n".join(sections)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": combined,
                }
            }
        )
    )


if __name__ == "__main__":
    main()
