from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "verify-prose-style.py"
CURSOR_PY_HOOK = (
    Path(__file__).resolve().parents[2] / "cursor" / "hooks" / "verify_python_lint.py"
)
CURSOR_MD_HOOK = (
    Path(__file__).resolve().parents[2] / "cursor" / "hooks" / "verify_prose_lint.py"
)

pytestmark = pytest.mark.skipif(shutil.which("vale") is None, reason="vale not on PATH")


def _hook(file: Path | str, stdin: str | None = None) -> str:
    """Run verify-prose-style hook and return its stdout."""
    event = (
        stdin
        if stdin is not None
        else json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(file)}})
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(HOOK)],
        input=event,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_clean_markdown_passes_silently(tmp_path: Path) -> None:
    """Verify compliant markdown with tech stack headings and first-person singular."""
    doc = tmp_path / "doc.md"
    doc.write_text(
        "## ArgoCD and BigQuery integration\n\n"
        "I configured the worker so it polls Redis every 16s on version 25.3.7033.\n"
    )

    assert _hook(doc) == ""


def test_flags_prose_violations(tmp_path: Path) -> None:
    """Verify first-person plural, jargon, filler, and vague links are flagged."""
    doc = tmp_path / "bad.md"
    doc.write_text(
        "## Executive Summary\n\n"
        "Note that we will hydrate the database in order to leverage it. "
        "Read more [click here](https://example.com).\n\n"
        "- **Bold title:** busy bullet text;\n"
    )

    raw = _hook(doc)
    assert raw != ""
    data = json.loads(raw)
    assert "additional_context" not in data
    context = data["hookSpecificOutput"]["additionalContext"]
    assert "Google.We" in context
    assert "House.WordList" in context
    assert "House.Filler" in context
    assert "House.Links" in context
    assert "House.BoldBullet" in context
    assert "House.ListPunctuation" in context


def test_flags_zero_quantifier_and_allows_numeric_zero(tmp_path: Path) -> None:
    """Verify quantifying 'zero' is flagged while numeric uses pass cleanly."""
    bad = tmp_path / "zero_bad.md"
    bad.write_text(
        "# Zero quantifier examples\n\n"
        "Run with zero imports and zero external dependencies.\n"
    )
    raw = _hook(bad)
    assert raw != ""
    context = json.loads(raw)["hookSpecificOutput"]["additionalContext"]
    assert "House.ZeroQuantifier" in context
    assert "House.ZeroQuantifierAdj" in context

    good = tmp_path / "zero_good.md"
    good.write_text(
        "# Valid numeric zero\n\n"
        "Set the counter to zero and use zero-based indexing.\n"
        "Exit code zero returns immediately after zero or more retries.\n"
        "Divide by zero errors fail validation.\n"
    )
    assert _hook(good) == ""


def test_lints_markdown_inside_git_worktree(tmp_path: Path) -> None:
    """Verify markdown files inside a .worktrees/<branch>/ directory are linted."""
    wt_doc = tmp_path / ".worktrees" / "feature-branch" / "docs" / "spec.md"
    wt_doc.parent.mkdir(parents=True)
    wt_doc.write_text(
        "## Overview\n\n"
        "- **Bold title:** busy bullet text.\n"
    )

    raw = _hook(wt_doc)
    assert raw != ""
    context = json.loads(raw)["hookSpecificOutput"]["additionalContext"]
    assert "House.BoldBullet" in context


def test_plans_directory_allows_future_tense_will(tmp_path: Path) -> None:
    """Verify that plans/ and proposals/ exempt future tense 'will'."""
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    plan_doc = plans_dir / "migration-plan.md"
    plan_doc.write_text("# Migration plan\n\nPhase 2 will migrate the database.\n")

    assert _hook(plan_doc) == ""


def test_skips_code_files(tmp_path: Path) -> None:
    """Verify that python files are ignored by the prose style hook."""
    code = tmp_path / "script.py"
    code.write_text("# we will hydrate\nx = 1\n")

    assert _hook(code) == ""


@pytest.mark.parametrize("filename", ["INDEX.md", "log.md", "CLAUDE.md", "AGENTS.md"])
def test_skips_excluded_markdown_files(tmp_path: Path, filename: str) -> None:
    """Verify generated indices, logs, and agent instruction files are skipped."""
    excluded = tmp_path / filename
    excluded.write_text("# System Topology\n\nWe will hydrate the wire format.\n")

    assert _hook(excluded) == ""


def test_skips_missing_files(tmp_path: Path) -> None:
    """Verify that non-existent paths exit silently."""
    missing = tmp_path / "missing.md"

    assert _hook(missing) == ""


def test_cursor_stop_hooks_do_not_clobber_tracking_log(tmp_path: Path) -> None:
    """Verify verify_python_lint preserves .md entries for verify_prose_lint."""
    track_dir = Path.home() / ".cursor/var/agent-edits"
    track_dir.mkdir(parents=True, exist_ok=True)
    gen_id = "test-gen-prose-preservation"
    log_file = track_dir / f"{gen_id}.txt"

    bad_md = tmp_path / "bad_turn.md"
    bad_md.write_text("# Overview\n\nWe will hydrate the service.\n")
    log_file.write_text(f"{bad_md}\n", encoding="utf-8")

    try:
        payload = json.dumps({"status": "completed", "generation_id": gen_id})
        py_res = subprocess.run(  # noqa: S603
            [sys.executable, str(CURSOR_PY_HOOK)],
            input=payload,
            capture_output=True,
            text=True,
            check=False,
        )
        assert json.loads(py_res.stdout) == {}
        assert log_file.is_file()

        md_res = subprocess.run(  # noqa: S603
            [sys.executable, str(CURSOR_MD_HOOK)],
            input=payload,
            capture_output=True,
            text=True,
            check=False,
        )
        followup = json.loads(md_res.stdout).get("followup_message", "")
        assert "Google.We" in followup
        assert "House.WordList" in followup
    finally:
        log_file.unlink(missing_ok=True)
