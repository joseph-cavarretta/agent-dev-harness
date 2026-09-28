from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "lint-autofix.py"

pytestmark = pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not on PATH")

RUFF_CONFIG = """[tool.ruff]
extend-exclude = ["skipped"]

[tool.ruff.lint]
select = ["F", "I"]
"""
MESSY = "import sys\nimport os\nx=[1,2 ,3]\nprint(os.sep,sys.argv,x)\n"
TIDY = "import os\nimport sys\n\nx = [1, 2, 3]\nprint(os.sep, sys.argv, x)\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text(RUFF_CONFIG)
    return tmp_path


def _hook(file: Path | str, stdin: str | None = None) -> str:
    event = (
        stdin
        if stdin is not None
        else json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(file)}})
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, HOOK], input=event, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_fixes_and_formats_silently(repo: Path) -> None:
    file = repo / "pkg" / "mod.py"
    file.parent.mkdir()
    file.write_text(MESSY)

    assert _hook(file) == ""
    assert file.read_text() == TIDY


@pytest.mark.parametrize("rel", ["mod.py", "pkg/sub/mod.py"], ids=["root", "nested"])
def test_reports_what_it_cannot_fix(repo: Path, rel: str) -> None:
    file = repo / rel
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("print(undefined_name)\n")

    context = json.loads(_hook(file))["hookSpecificOutput"]["additionalContext"]

    assert "mod.py:1:7: F821" in context


def test_python_shebang_script_without_extension(repo: Path) -> None:
    file = repo / "ah-tool"
    file.write_text("#!/usr/bin/env -S uv run --script\n" + MESSY)

    _hook(file)

    assert file.read_text().endswith(TIDY)


@pytest.mark.parametrize(
    ("name", "text"),
    [("notes.md", MESSY), ("run.sh", "#!/bin/sh\n" + MESSY), ("skipped/mod.py", MESSY)],
    ids=["markdown", "shell-script", "excluded-path"],
)
def test_leaves_other_files_alone(repo: Path, name: str, text: str) -> None:
    file = repo / name
    file.parent.mkdir(exist_ok=True)
    file.write_text(text)

    assert _hook(file) == ""
    assert file.read_text() == text


def test_repo_without_ruff_config_is_untouched(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    file = tmp_path / "mod.py"
    file.write_text(MESSY)

    assert _hook(file) == ""
    assert file.read_text() == MESSY


@pytest.mark.parametrize(
    "stdin",
    ["not json", "{}", json.dumps({"tool_input": {"file_path": "/no/such/file.py"}})],
    ids=["bad-json", "no-path", "missing-file"],
)
def test_bad_events_are_ignored(stdin: str) -> None:
    assert _hook("", stdin=stdin) == ""
