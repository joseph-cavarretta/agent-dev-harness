#!/usr/bin/env python3
"""PostToolUse / AfterTool: append shell and file-read tool calls to a per-session audit log.

Log format (one entry per call):
    2026-04-21T09:42:15 exit=0  [cwd=/path]
      $ <command>
    2026-04-21T09:42:20  [cwd=/path]
      @ Grep 'pattern' in /some/path

Claude (Bash, Read, Grep, Glob) entries → ~/.claude/audit/<session_id>.log
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
SHELL_TOOLS = ("Bash", "run_shell_command")
# Claude's built-in read tools, logged so repeated reads (e.g. of the vault) can be
# counted alongside shell commands.
FILE_TOOLS = ("Read", "Grep", "Glob")


def describe(tool_name: str, tool_input: dict) -> str:
    """The logged line: `$ command` for shells, `@ Tool target` for file reads."""
    if tool_name in SHELL_TOOLS:
        return f"$ {tool_input.get('command', '')}"
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    if tool_name == "Read":
        return f"@ Read {path}"
    return f"@ {tool_name} {tool_input.get('pattern', '')!r} in {path or '.'}"


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    tool_name = event.get("tool_name")
    if tool_name not in SHELL_TOOLS + FILE_TOOLS:
        return 0
    log_dir = LOG_DIR_GEMINI if tool_name == "run_shell_command" else LOG_DIR_CLAUDE

    session_id = event.get("session_id", "unknown")
    cwd = event.get("cwd", "?")
    line = describe(tool_name, event.get("tool_input") or {})
    # File tools can return non-dict responses; only shells report an exit code.
    response = event.get("tool_response")
    status = ""
    if isinstance(response, dict):
        status = response.get("exit_code", response.get("exitCode", ""))

    try:
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, f"{session_id}.log")
        with open(path, "a") as f:
            ts = datetime.now().isoformat(timespec="seconds")
            status_s = f" exit={status}" if status != "" else ""
            f.write(f"{ts}{status_s}  [cwd={cwd}]\n  {line}\n")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
