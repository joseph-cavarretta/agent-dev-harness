from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "pr-prose-guard.py"

pytestmark = pytest.mark.skipif(shutil.which("vale") is None, reason="vale not on PATH")


def _run_hook(command: str) -> subprocess.CompletedProcess[str]:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    return subprocess.run(  # noqa: S603
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )


def test_allows_clean_gh_pr_create_heredoc() -> None:
    cmd = (
        'gh pr create --draft --title "feat(iam): merge role" --body "$(cat <<\'EOF\'\n'
        "## What\n\n"
        "Merges the legacy custom role into `developer`.\n\n"
        "- Added read permissions for local sandboxes.\n"
        "- Dropped unused bucket permissions.\n"
        'EOF\n)"'
    )
    res = _run_hook(cmd)
    assert res.returncode == 0
    assert res.stdout == ""


def test_denies_bold_bullet_and_editorial_we_in_gh_pr_create() -> None:
    cmd = (
        'gh pr create --title "feat(x): y" --body "$(cat <<\'EOF\'\n'
        "## Summary\n\n"
        "We will hydrate the cache.\n\n"
        "- **Added:** something important.\n"
        'EOF\n)"'
    )
    res = _run_hook(cmd)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = data["hookSpecificOutput"]["permissionDecisionReason"]
    assert "Google.We" in reason
    assert "House.BoldBullet" in reason


def test_checks_inline_body_on_gh_pr_edit() -> None:
    bad_cmd = 'gh pr edit 42 --body "## Overview\n\n- **Title:** bold lead-in."'
    bad_res = _run_hook(bad_cmd)
    assert bad_res.returncode == 0
    reason = json.loads(bad_res.stdout)["hookSpecificOutput"][
        "permissionDecisionReason"
    ]
    assert "House.BoldBullet" in reason

    good_cmd = 'gh pr edit 42 --body "## Overview\n\nUpdates the IAM policy."'
    good_res = _run_hook(good_cmd)
    assert good_res.returncode == 0
    assert good_res.stdout == ""


def test_checks_gh_api_pulls_patch_and_skips_pr_comments() -> None:
    bad_api = (
        "gh api repos/acme/infra-config/pulls/42 -X PATCH "
        "-f body=\"$(cat <<'EOF'\n## Overview\n\nWe will leverage this.\nEOF\n)\""
    )
    res = _run_hook(bad_api)
    assert res.returncode == 0
    reason = json.loads(res.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "Google.We" in reason

    comment_api = (
        'gh api repos/acme/infra-config/pulls/42/comments -f body="We will fix this."'
    )
    comment_res = _run_hook(comment_api)
    assert comment_res.returncode == 0
    assert comment_res.stdout == ""


def test_checks_body_file_relative_to_cd_directory(tmp_path: Path) -> None:
    body_file = tmp_path / "pr_body.md"
    body_file.write_text("## System Topology\n\nWe will hydrate it.\n")
    cmd = f"cd {tmp_path} && gh pr create --title 'docs: update' --body-file pr_body.md"

    res = _run_hook(cmd)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    reason = data["hookSpecificOutput"]["permissionDecisionReason"]
    assert "House.Headings" in reason
    assert "Google.We" in reason


def test_ignores_non_pr_commands_and_read_queries() -> None:
    for cmd in (
        "gh pr checks 42",
        "gh pr view 42 --json body",
        "git status",
    ):
        res = _run_hook(cmd)
        assert res.returncode == 0
        assert res.stdout == ""
