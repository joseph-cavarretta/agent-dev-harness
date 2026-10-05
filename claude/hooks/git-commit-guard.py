#!/usr/bin/env python3
"""PreToolUse on Bash: block git commits whose message is not `type(scope): subject`.

The subject must be one line of at most 50 characters with no body. Co-Authored-By
trailers are dropped before checking, in case one slips past the attribution setting.
"""

import json
import re
import sys

VALID_TYPES = ("feat", "fix", "docs", "refactor", "test", "chore")
MAX_SUBJECT_LENGTH = 50
FORMAT_HELP = (
    f"Required: type(scope): description  (≤{MAX_SUBJECT_LENGTH} chars, single line)\n"
    f"Types: {', '.join(VALID_TYPES)}"
)
SUBJECT_PATTERN = r"^(" + "|".join(VALID_TYPES) + r")\([^)]+\): .+"
HEREDOC_PATTERN = r"cat <<'EOF'\s*\n(.*?)^\s*EOF"
FLAG_PATTERN = r'-m\s+(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*?)\')'


def deny(reason: str) -> None:
    """Print a PreToolUse deny decision and stop."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def meaningful_lines(text: str) -> list[str]:
    """Return non-empty lines, excluding Co-Authored-By trailers."""
    stripped = (line.strip() for line in text.splitlines())
    return [
        line
        for line in stripped
        if line and not line.lower().startswith("co-authored-by:")
    ]


def message_lines(command: str) -> list[str] | None:
    """Commit message lines from a heredoc or `-m` flag, or None if neither is found."""
    heredoc = re.search(HEREDOC_PATTERN, command, re.DOTALL | re.MULTILINE)
    if heredoc:
        return meaningful_lines(heredoc.group(1))
    flag = re.search(FLAG_PATTERN, command)
    if flag:
        return meaningful_lines(flag.group(1) or flag.group(2))
    return None


def main() -> None:
    """Deny the commit when its message breaks the format; otherwise do nothing."""
    command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    if "git commit" not in command:
        return

    lines = message_lines(command)
    if not lines:
        return  # Unrecognised format: let it through
    subject = lines[0]

    if len(lines) > 1:
        deny(
            "Commit message must be a single subject line — no body allowed.\n"
            f"{FORMAT_HELP}"
        )
    if len(subject) > MAX_SUBJECT_LENGTH:
        deny(
            f"Commit message too long: {len(subject)} chars "
            f"(max {MAX_SUBJECT_LENGTH}).\nGot: '{subject}'\n{FORMAT_HELP}"
        )
    if not re.match(SUBJECT_PATTERN, subject):
        deny(f"Bad commit format: '{subject}'\n{FORMAT_HELP}")


if __name__ == "__main__":
    main()
