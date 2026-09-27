from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / "claude" / "hooks" / "tools-index.py"


def _script(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(body)
    path.chmod(0o755)


def _run(path: str) -> str:
    return subprocess.run(  # noqa: S603
        [sys.executable, HOOK], capture_output=True, text=True, check=True,
        env={"PATH": path},
    ).stdout  # fmt: skip


def test_lists_installed_scripts_with_summaries(tmp_path: Path) -> None:
    _script(tmp_path, "ah-b", "#!/bin/sh\n# summary: second tool\n")
    _script(tmp_path, "ah-a", "#!/bin/sh\n# summary: first tool\n")
    _script(tmp_path, "other", "#!/bin/sh\n# summary: not ours\n")

    lines = _run(str(tmp_path)).splitlines()

    assert lines[1:] == ["- `ah-a`: first tool", "- `ah-b`: second tool"]


def test_earlier_path_entry_wins(tmp_path: Path) -> None:
    first, second = tmp_path / "1", tmp_path / "2"
    first.mkdir()
    second.mkdir()
    _script(first, "ah-x", "# summary: first\n")
    _script(second, "ah-x", "# summary: shadowed\n")

    assert "shadowed" not in _run(f"{first}:{second}")


def test_prints_nothing_without_scripts(tmp_path: Path) -> None:
    assert _run(str(tmp_path)) == ""
