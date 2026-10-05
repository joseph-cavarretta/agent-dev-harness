from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "ah-check"

pytestmark = pytest.mark.skipif(shutil.which("uvx") is None, reason="needs uvx")

CONFIG = """[tool.ruff.lint]
select = ["F"]

[tool.mypy]
strict = true
"""
USAGE_ERROR = 2
LIMIT = 2
CLEAN = "def add(a: int, b: int) -> int:\n    return a + b\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # noqa: S603, S607
    (tmp_path / "pyproject.toml").write_text(CONFIG)
    (tmp_path / "calc.py").write_text(CLEAN)
    return tmp_path


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [SCRIPT, str(repo), *args], capture_output=True, text=True, check=False
    )


# Rows are ah-check --json output parsed as-is; each test reads the keys it asserts on.
def _checks(repo: Path, *args: str) -> dict[str, dict[str, Any]]:
    out = _run(repo, *args, "--json").stdout
    return {c["name"]: c for c in map(json.loads, out.splitlines())}


def test_clean_repo_passes(repo: Path) -> None:
    (repo / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add() -> None:\n    assert add(1, 2) == 3\n"
    )

    result = _run(repo)

    assert result.returncode == 0, result.stdout
    assert result.stdout.startswith("4/4 checks passed")


def test_reports_only_failing_lines(repo: Path) -> None:
    (repo / "bad.py").write_text("x=1\nprint(missing)\n")
    (repo / "test_calc.py").write_text(
        "def test_ok() -> None:\n    assert True\n\n\n"
        'def test_bad() -> None:\n    assert 1 == 2, "boom"\n'
    )

    checks = _checks(repo)

    assert checks["ruff"]["details"] == ["bad.py:2:7: F821 Undefined name `missing`"]
    assert checks["format"]["details"] == ["bad.py"]
    assert any("bad.py:2: error:" in d for d in checks["mypy"]["details"])
    assert checks["pytest"]["details"] == [
        "FAILED test_calc.py::test_bad - AssertionError: boom"
    ]
    assert checks["pytest"]["summary"].startswith("1 failed, 1 passed")
    assert _run(repo).returncode == 1


def test_collection_error_gets_its_reason(repo: Path) -> None:
    (repo / "test_broken.py").write_text("import no_such_module\n")

    details = _checks(repo, "--only", "pytest")["pytest"]["details"]

    assert details == [
        "ERROR test_broken.py - ModuleNotFoundError: No module named 'no_such_module'"
    ]


def test_skips_what_the_repo_does_not_configure(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # noqa: S603, S607
    (tmp_path / "calc.py").write_text(CLEAN)

    checks = _checks(tmp_path)

    assert {n: c["status"] for n, c in checks.items()} == dict.fromkeys(
        ("ruff", "format", "mypy", "pytest"), "skip"
    )
    # A verifier must not pass when nothing was checked.
    assert _run(tmp_path).returncode == 1


def test_never_creates_an_environment(repo: Path) -> None:
    (repo / "uv.lock").write_text("")
    (repo / "test_calc.py").write_text("def test_ok() -> None:\n    assert True\n")

    checks = _checks(repo, "--only", "mypy,pytest")

    assert checks["pytest"]["status"] == "skip"
    assert "uv sync" in checks["pytest"]["summary"]
    assert not (repo / ".venv").exists()


def test_leaves_no_caches_behind(repo: Path) -> None:
    (repo / "test_calc.py").write_text("def test_ok() -> None:\n    assert True\n")

    _run(repo)

    left = {
        p.name
        for p in repo.rglob("*")
        if p.name.endswith("cache") or p.name == "__pycache__"
    }
    assert not left


def test_limit_caps_details(repo: Path) -> None:
    (repo / "bad.py").write_text("".join(f"print(m{i})\n" for i in range(5)))

    out = _run(repo, "--only", "ruff", "--limit", str(LIMIT)).stdout

    assert out.count("F821") == LIMIT
    assert "3 more" in out


def test_outside_a_repo_is_an_error(tmp_path: Path) -> None:
    result = _run(tmp_path / "nowhere")

    assert result.returncode == USAGE_ERROR
    assert "not inside a git repo" in result.stderr


def test_unknown_check_is_rejected(repo: Path) -> None:
    assert _run(repo, "--only", "eslint").returncode == USAGE_ERROR
