from __future__ import annotations

import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "ah-repo-status"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)  # noqa: S603, S607


def _make_repo(root: Path, name: str) -> Path:
    repo = root / name
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
         "--allow-empty", "-m", "init")  # fmt: skip
    return repo


def _run(root: Path, *flags: str) -> list[dict[str, object]]:
    out = subprocess.run(  # noqa: S603
        [SCRIPT, "--root", str(root), "--no-pr", "--json", *flags],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [json.loads(line) for line in out.splitlines()]


def test_counts_modified_untracked_and_stashes(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, "busy")
    (repo / "tracked").write_text("a")
    _git(repo, "add", "tracked")
    (repo / "loose").write_text("b")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "stash", "-q")
    (repo / "tracked").write_text("c")
    _git(repo, "add", "tracked")

    [status] = _run(tmp_path)

    assert status["branch"] == "main"
    assert status["modified"] == 1
    assert status["untracked"] == 1
    assert status["stashes"] == 1
    assert status["upstream"] is None


def test_dirty_hides_clean_repos(tmp_path: Path) -> None:
    _make_repo(tmp_path, "clean")
    dirty = _make_repo(tmp_path, "dirty")
    (dirty / "new").write_text("x")

    assert [s["name"] for s in _run(tmp_path, "--dirty")] == ["dirty"]


def test_does_not_touch_the_index(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, "r")
    index = repo / ".git" / "index"
    before = index.stat().st_mtime_ns if index.exists() else None

    _run(tmp_path)

    after = index.stat().st_mtime_ns if index.exists() else None
    assert before == after
