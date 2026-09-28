from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AH_CHECK = REPO / "tools" / "bin" / "ah-check"

pytestmark = pytest.mark.skipif(
    shutil.which("uvx") is None or shutil.which("uv") is None, reason="needs uv"
)


def test_generated_project_passes_ah_check(tmp_path: Path) -> None:
    dest = tmp_path / "order-sync"
    subprocess.run(  # noqa: S603
        ["make", "-C", str(REPO), "new-project", f"DEST={dest}"],  # noqa: S607
        check=True,
        capture_output=True,
    )

    result = subprocess.run(  # noqa: S603
        [AH_CHECK, str(dest)], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stdout
    assert result.stdout.startswith("4/4 checks passed")
    assert (
        "class OrderSyncError(Exception):"
        in (dest / "src/order_sync/errors.py").read_text()
    )


def test_refuses_to_overwrite(tmp_path: Path) -> None:
    result = subprocess.run(  # noqa: S603
        ["make", "-C", str(REPO), "new-project", f"DEST={tmp_path}"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "already exists" in result.stdout
