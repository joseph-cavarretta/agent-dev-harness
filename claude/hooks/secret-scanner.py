#!/usr/bin/env python3
"""PreToolUse hook: block Write/Edit if content contains high-confidence secrets."""
import json
import re
import sys

data = json.load(sys.stdin)
tool_name = data.get("tool_name", "")

if tool_name == "Write":
    content = data.get("tool_input", {}).get("content", "")
    file_path = data.get("tool_input", {}).get("file_path", "")
elif tool_name == "Edit":
    content = data.get("tool_input", {}).get("new_string", "")
    file_path = data.get("tool_input", {}).get("file_path", "")
else:
    sys.exit(0)

# Skip hook scripts themselves (contain pattern strings that would self-match)
if "/.claude/hooks/" in file_path:
    sys.exit(0)

# High-confidence patterns only — specific enough to have near-zero false positives
SECRET_PATTERNS = [
    (r"-----BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY", "private key"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
    (r"AIza[0-9A-Za-z\-_]{35}", "Google API key"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub personal access token"),
    (r"ghs_[A-Za-z0-9]{36}", "GitHub Actions token"),
    (r'"private_key":\s*"-----BEGIN', "GCP service account key"),
    (r"sk-ant-api\w{20,}", "Anthropic API key"),
    (r"(?i)(openai_api_key|anthropic_api_key)\s*=\s*['\"]?[A-Za-z0-9\-_]{20,}", "AI API key assignment"),
]

findings = []
for pattern, label in SECRET_PATTERNS:
    if re.search(pattern, content):
        findings.append(label)

if findings:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Secret scanner blocked write to {file_path}: "
                f"detected {', '.join(findings)}. "
                "Use environment variables or a secret manager instead."
            ),
        }
    }))
