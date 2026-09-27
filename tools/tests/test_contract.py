"""Contract every script in tools/bin must meet; see tools/README.md."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "tools" / "bin"
SUMMARY_PREFIX = "# summary:"
# The summary is injected into every session, so it has to stay one short line.
MAX_SUMMARY = 200

SCRIPTS = sorted(p for p in BIN.iterdir() if not p.name.startswith("."))


def _summary(script: Path) -> str | None:
    for line in script.read_text().splitlines()[:20]:
        if line.startswith(SUMMARY_PREFIX):
            return line.removeprefix(SUMMARY_PREFIX).strip()
    return None


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_script_contract(script: Path) -> None:
    assert script.name.startswith("ah-"), "scripts must use the ah- prefix"
    assert os.access(script, os.X_OK), "script is not executable"
    summary = _summary(script)
    assert summary, f"needs a `{SUMMARY_PREFIX}` line in its first 20 lines"
    assert len(summary) <= MAX_SUMMARY, f"summary over {MAX_SUMMARY} chars"
    # Scripts come from this repo, not from input.
    result = subprocess.run(  # noqa: S603
        [script, "--help"], capture_output=True, timeout=30, check=False
    )
    assert result.returncode == 0, "--help must exit 0"
