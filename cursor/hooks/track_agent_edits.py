#!/usr/bin/env python3
"""Record file paths edited by an agent during a session or turn."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

TRACK_DIR = Path.home() / ".cursor/var/agent-edits"
MAX_AGE_SECONDS = 86400  # 1 day


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


def _cleanup_old_records(track_dir: Path) -> None:
    """Purge tracking files older than max age."""
    now = time.time()
    try:
        for entry in track_dir.glob("*.txt"):
            if now - entry.stat().st_mtime > MAX_AGE_SECONDS:
                entry.unlink(missing_ok=True)
    except OSError:
        pass


def main() -> None:
    """Read hook event and write edited python or markdown path to tracking store."""
    try:
        data: dict[str, object] = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        sys.exit(0)

    path_str = _extract_file_path(data)
    if not path_str or not path_str.endswith((".py", ".md", ".mdx")):
        sys.exit(0)

    gen_id = data.get("generation_id")
    conv_id = data.get("conversation_id") or data.get("session_id")

    keys: list[str] = [
        str(k) for k in (gen_id, conv_id) if isinstance(k, str) and k
    ]
    if not keys:
        keys = ["latest"]

    try:
        TRACK_DIR.mkdir(parents=True, exist_ok=True)
        _cleanup_old_records(TRACK_DIR)
        resolved_path = str(Path(path_str).resolve())
        for key in keys:
            target_log = TRACK_DIR / f"{key}.txt"
            with target_log.open("a", encoding="utf-8") as f:
                f.write(f"{resolved_path}\n")
    except OSError:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
