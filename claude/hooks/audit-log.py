#!/usr/bin/env python3
"""PostToolUse / AfterTool: append every shell tool call to a per-session audit log.

Log format (one entry per call):
    2026-04-21T09:42:15 exit=0  [cwd=/path]
      $ <command>

Claude (Bash) entries  → ~/.claude/audit/<session_id>.log
Gemini (run_shell_command) entries → ~/.gemini/audit/<session_id>.log
Non-blocking (always exit 0).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

LOG_DIR_CLAUDE = os.path.expanduser("~/.claude/audit")
LOG_DIR_GEMINI = os.path.expanduser("~/.gemini/audit")


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    tool_name = event.get("tool_name")
    if tool_name not in ("Bash", "run_shell_command"):
        return 0
    log_dir = LOG_DIR_GEMINI if tool_name == "run_shell_command" else LOG_DIR_CLAUDE

    session_id = event.get("session_id", "unknown")
    cwd = event.get("cwd", "?")
    cmd = (event.get("tool_input") or {}).get("command", "")
    response = event.get("tool_response") or {}
    status = response.get("exit_code", response.get("exitCode", ""))

    try:
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, f"{session_id}.log")
        with open(path, "a") as f:
            ts = datetime.now().isoformat(timespec="seconds")
            status_s = f" exit={status}" if status != "" else ""
            f.write(f"{ts}{status_s}  [cwd={cwd}]\n  $ {cmd}\n")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
