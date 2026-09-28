from __future__ import annotations

import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "ah-tools-stats"

SESSION_A = """\
2026-09-20T10:00:00 exit=0  [cwd=/r]
  $ cd ~/.vault && grep -ril bloom wiki
2026-09-20T10:01:00  [cwd=/r]
  @ Read /home/me/.vault/wiki/repos/sketches.md
2026-09-20T10:02:00 exit=0  [cwd=/r]
  $ ah-vault-find bloom filter
2026-09-20T10:03:00 exit=0  [cwd=/r]
  $ cd ~/dev/x && uvx ruff check . && uvx pytest -q
2026-09-20T10:04:00 exit=0  [cwd=/r]
  $ cd ~/.vault && python3 - <<'EOF'
print("ruff check inside a heredoc is not a command")
EOF
2026-09-20T10:05:00 exit=0  [cwd=/r]
  $ git add pytest.ini && git diff --cached --stat
"""
SESSION_B = """\
2026-09-25T09:00:00 exit=1  [cwd=/r]
  $ ah-check ~/dev/x
2026-09-25T09:01:00 exit=0  [cwd=/r]
  $ for d in ~/dev/*/; do git -C $d status --short; done
""" + "".join(
    f"2026-09-25T09:0{i}:30 exit=0  [cwd=/r]\n  $ cd ~/dev/x && sed -n 1,{i}0p f.py\n"
    for i in range(2, 6)
)
Rows = list[dict[str, object]]


def _stats(tmp_path: Path, *args: str) -> tuple[dict[str, dict[str, object]], Rows]:
    (tmp_path / "a.log").write_text(SESSION_A)
    (tmp_path / "b.log").write_text(SESSION_B)
    out = subprocess.run(  # noqa: S603
        [SCRIPT, "--audit-dir", str(tmp_path), "--json", *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    rows = [json.loads(line) for line in out.splitlines()]
    tools = {str(r["tool"]): r for r in rows if "tool" in r}
    return tools, [r for r in rows if "command" in r]


def test_counts_tool_use_against_raw_calls(tmp_path: Path) -> None:
    tools, _ = _stats(tmp_path)

    vault, check = tools["ah-vault-find"], tools["ah-check"]
    assert (vault["tool_calls"], vault["raw_calls"]) == (1, 2)
    assert (check["tool_calls"], check["raw_calls"]) == (1, 1)
    assert tools["ah-repo-status"]["raw_calls"] == 1


def test_ignores_heredoc_bodies_edits_and_file_names(tmp_path: Path) -> None:
    tools, _ = _stats(tmp_path)

    # The heredoc's "ruff check", the vault edit script and `git add pytest.ini`
    # would each inflate these counts if matched.
    assert tools["ah-check"]["raw_calls"] == 1
    assert tools["ah-vault-find"]["examples"] == [
        "$ cd ~/.vault && grep -ril bloom wiki",
        "@ Read /home/me/.vault/wiki/repos/sketches.md",
    ]


def test_candidates_are_repeated_reads_only(tmp_path: Path) -> None:
    _, candidates = _stats(tmp_path)

    assert [(c["command"], c["count"]) for c in candidates] == [("sed -n", 4)]


def test_since_filters_by_time(tmp_path: Path) -> None:
    tools, _ = _stats(tmp_path, "--since", "2026-09-24")

    assert tools["ah-vault-find"]["raw_calls"] == 0
    assert tools["ah-check"]["tool_calls"] == 1


def test_missing_audit_dir_is_an_error(tmp_path: Path) -> None:
    result = subprocess.run(  # noqa: S603
        [SCRIPT, "--audit-dir", str(tmp_path / "none")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "no audit log" in result.stderr


def test_zero_examples_means_none(tmp_path: Path) -> None:
    tools, _ = _stats(tmp_path, "--examples", "0")

    assert all(t["examples"] == [] for t in tools.values())
