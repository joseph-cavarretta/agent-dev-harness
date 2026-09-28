"""Contract every script in tools/bin must meet; see tools/README.md."""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
# The hook's filename has a hyphen, so it can't be imported by name.
_spec = importlib.util.spec_from_file_location(
    "tools_index", REPO / "claude" / "hooks" / "tools-index.py"
)
assert _spec is not None
assert _spec.loader is not None
tools_index = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tools_index)

BIN = REPO / "tools" / "bin"
SUMMARY_PREFIX = "# summary:"
# The summary is injected into every session, so it has to stay short.
MAX_SUMMARY = 200

SCRIPTS = sorted(p for p in BIN.iterdir() if not p.name.startswith("."))


def _summary(script: Path) -> str | None:
    """The summary exactly as the tools-index hook will read it."""
    return tools_index.summary(script)


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
