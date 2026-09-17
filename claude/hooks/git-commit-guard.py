#!/usr/bin/env python3
"""Validates git commit message format. Blocks commits that don't match
type(scope): description  (≤50 chars, single line, no body).
Co-Authored-By lines are excluded before validation (attribution setting
prevents them from appearing, but this handles any that slip through)."""
import json
import re
import sys

data = json.load(sys.stdin)
command = data.get("tool_input", {}).get("command", "")

if "git commit" not in command:
    sys.exit(0)

VALID_TYPES = ("feat", "fix", "docs", "refactor", "test", "chore")
FORMAT_HELP = (
    f"Required: type(scope): description  (≤50 chars, single line)\n"
    f"Types: {', '.join(VALID_TYPES)}"
)


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def meaningful_lines(text):
    """Return non-empty lines, excluding Co-Authored-By trailers."""
    return [
        l.strip() for l in text.splitlines()
        if l.strip() and not l.strip().lower().startswith("co-authored-by:")
    ]


# Extract commit message — try heredoc form first, then -m flag
subject = None
has_body = False

heredoc = re.search(r"cat <<'EOF'\s*\n(.*?)^\s*EOF", command, re.DOTALL | re.MULTILINE)
if heredoc:
    lines = meaningful_lines(heredoc.group(1))
    subject = lines[0] if lines else None
    has_body = len(lines) > 1
else:
    m = re.search(r'-m\s+(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*?)\')', command)
    if m:
        raw = m.group(1) or m.group(2)
        lines = meaningful_lines(raw)
        subject = lines[0] if lines else None
        has_body = len(lines) > 1

if subject is None:
    sys.exit(0)  # Unrecognised format — let it through

if has_body:
    deny(f"Commit message must be a single subject line — no body allowed.\n{FORMAT_HELP}")

if len(subject) > 50:
    deny(f"Commit message too long: {len(subject)} chars (max 50).\nGot: '{subject}'\n{FORMAT_HELP}")

pattern = r"^(" + "|".join(VALID_TYPES) + r")\([^)]+\): .+"
if not re.match(pattern, subject):
    deny(f"Bad commit format: '{subject}'\n{FORMAT_HELP}")
