#!/usr/bin/env python3
"""SessionStart: list the ah-* scripts on PATH so every session knows they exist.

Stdout from a SessionStart hook is added to the model's context. Each script
describes itself with a `# summary:` line, so there is no separate list to keep in
sync: install a script and the next session sees it. Scripts are read, never run.
Non-blocking (always exit 0).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SUMMARY_PREFIX = "# summary:"
CONTINUATION = "#   "
HEADER = (
    "Local tools: read-only `ah-*` scripts on PATH that print summaries instead of "
    "raw output. Prefer them to improvised commands when one fits. `<name> --help` "
    "shows flags; `--json` prints JSON lines for piping."
)


def summary(script: Path) -> str | None:
    """The script's `# summary:` text from its first 20 lines.

    Following lines that start with `#   ` continue it, so scripts can wrap the summary
    to their line-length limit.
    """
    try:
        with script.open(encoding="utf-8", errors="replace") as f:
            head = [line.rstrip("\n") for _, line in zip(range(20), f, strict=False)]
    except OSError:
        return None
    for n, line in enumerate(head):
        if line.startswith(SUMMARY_PREFIX):
            parts = [line.removeprefix(SUMMARY_PREFIX).strip()]
            for more in head[n + 1 :]:
                if not more.startswith(CONTINUATION):
                    break
                parts.append(more.removeprefix(CONTINUATION).strip())
            return " ".join(parts)
    return None


def installed_scripts() -> dict[str, Path]:
    """First `ah-*` of each name on PATH, matching what the shell would run."""
    found: dict[str, Path] = {}
    for directory in os.get_exec_path():
        try:
            entries = sorted(Path(directory).glob("ah-*"))
        except OSError:
            continue
        for entry in entries:
            if entry.name not in found and os.access(entry, os.X_OK):
                found[entry.name] = entry
    return found


def main() -> int:
    """Print the header and one line per installed script, or nothing if none."""
    lines = [
        f"- `{name}`: {summary(path) or 'no summary; run --help'}"
        for name, path in sorted(installed_scripts().items())
    ]
    if lines:
        print("\n".join([HEADER, *lines]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
