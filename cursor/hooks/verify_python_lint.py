#!/usr/bin/env python3
"""Cursor stop hook to gate completion on strict python linting.

Lints the committable python files the agent touched this turn with the
agent-dev-harness ruff baseline and docstring check. If violations are found,
returns a followup_message to force agent remediation.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# directories skipped by default (scratch, loose, envs, tools)
SKIP_PATTERN = re.compile(
    r"(^|/)(\.local|\.claude|\.worktrees|worktrees|\.venv|venv|node_modules|scripts)/"
)
TRACK_DIR = Path.home() / ".cursor/var/agent-edits"
STYLEGUIDE_DIR = Path.home() / "dev/agent-dev-harness/python-styleguide"
RUFF_CONFIG = STYLEGUIDE_DIR / "ruff-base.toml"
DOCSTRING_CHECK = STYLEGUIDE_DIR / "docstring_length.py"
RUFF_VERSION = "0.16.4"
# ruff and docstring_length.py exit 1 for violations; other codes mean the tool broke
VIOLATIONS_FOUND = 1


def _find_workspace_root(payload: dict[str, object]) -> Path:
    """Find the active workspace root directory from hook payload."""
    roots = payload.get("workspace_roots")
    if (
        isinstance(roots, list)
        and roots
        and isinstance(roots[0], str)
        and Path(roots[0]).is_dir()
    ):
        return Path(roots[0])
    return Path.cwd()


def _get_git_root(cwd: Path) -> Path | None:
    """Find top-level git directory if current path is in a repository."""
    git_bin = shutil.which("git")
    if not git_bin:
        return None
    try:
        proc = subprocess.run(  # noqa: S603  # trusted system git binary
            [git_bin, "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(proc.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _committable_repo(path: Path) -> Path | None:
    """Return the repo that would commit this file, or None if git would not."""
    git_bin = shutil.which("git")
    repo_root = _get_git_root(path.parent)
    if not git_bin or repo_root is None:
        return None
    # check-ignore exits 0 when ignored, 1 when not, and 128 on error
    proc = subprocess.run(  # noqa: S603  # trusted system git binary
        [git_bin, "check-ignore", "-q", str(path)],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    return repo_root if proc.returncode == 1 else None


def _read_tracked_paths(file_path: Path) -> set[str]:
    """Read recorded python file paths from a tracking log."""
    paths: set[str] = set()
    if not file_path.is_file():
        return paths
    try:
        for line in file_path.read_text(encoding="utf-8").splitlines():
            cleaned = line.strip()
            if cleaned.endswith(".py"):
                paths.add(cleaned)
    except OSError:
        pass
    return paths


def _collect_target_files(
    payload: dict[str, object], git_root: Path | None
) -> dict[Path, list[str]]:
    """Group committable python files edited during this turn or task by repo."""
    candidates: set[str] = set()

    # subagentstop payload includes modified_files
    raw_modified = payload.get("modified_files")
    if isinstance(raw_modified, list):
        candidates.update(
            item
            for item in raw_modified
            if isinstance(item, str) and item.endswith(".py")
        )

    # turn-level edits recorded by afterfileedit / posttooluse
    gen_id = payload.get("generation_id")
    if isinstance(gen_id, str) and gen_id:
        candidates.update(_read_tracked_paths(TRACK_DIR / f"{gen_id}.txt"))

    # pending remediation files if inside a retry loop
    conv_id = payload.get("conversation_id") or payload.get("session_id")
    loop_count = payload.get("loop_count", 0)
    if (
        isinstance(loop_count, int)
        and loop_count > 0
        and isinstance(conv_id, str)
        and conv_id
    ):
        candidates.update(_read_tracked_paths(TRACK_DIR / f"{conv_id}_pending.txt"))

    targets: dict[Path, list[str]] = {}
    for candidate in sorted(candidates):
        path_obj = Path(candidate)
        if not path_obj.is_absolute() and git_root:
            path_obj = git_root / path_obj
        resolved = path_obj.resolve()
        if not resolved.is_file() or SKIP_PATTERN.search(str(resolved)):
            continue
        repo_root = _committable_repo(resolved)
        if repo_root is not None:
            targets.setdefault(repo_root, []).append(str(resolved))

    return targets


def _strip_extensions_from_log(log_file: Path, suffixes: tuple[str, ...]) -> None:
    """Remove matching file entries from a turn tracking log, unlinking if empty."""
    if not log_file.is_file():
        return
    try:
        remaining = [
            line
            for line in log_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().endswith(suffixes)
        ]
        if remaining:
            log_file.write_text("\n".join(remaining) + "\n", encoding="utf-8")
        else:
            log_file.unlink(missing_ok=True)
    except OSError:
        pass


def _cleanup_turn_records(
    payload: dict[str, object], *, clear_pending: bool
) -> None:
    """Remove python tracking records for this turn without clobbering prose entries."""
    gen_id = payload.get("generation_id")
    conv_id = payload.get("conversation_id") or payload.get("session_id")
    if isinstance(gen_id, str) and gen_id:
        _strip_extensions_from_log(TRACK_DIR / f"{gen_id}.txt", (".py",))
    if clear_pending and isinstance(conv_id, str) and conv_id:
        (TRACK_DIR / f"{conv_id}_pending.txt").unlink(missing_ok=True)


def _save_pending_records(
    payload: dict[str, object], files: list[str]
) -> None:
    """Save pending files to verify on subsequent remediation loops."""
    conv_id = payload.get("conversation_id") or payload.get("session_id")
    if not isinstance(conv_id, str) or not conv_id:
        return
    pending_file = TRACK_DIR / f"{conv_id}_pending.txt"
    try:
        TRACK_DIR.mkdir(parents=True, exist_ok=True)
        pending_file.write_text("\n".join(files) + "\n", encoding="utf-8")
    except OSError:
        pass


def _run_checks_by_repo(
    uvx_bin: str, targets_by_repo: dict[Path, list[str]]
) -> tuple[list[str], list[str]]:
    """Run ruff and docstring_length against target files grouped by repo."""
    checks = [
        [
            uvx_bin,
            f"ruff@{RUFF_VERSION}",
            "check",
            "--config",
            str(RUFF_CONFIG),
            "--force-exclude",
            "--output-format",
            "concise",
        ],
        [sys.executable, str(DOCSTRING_CHECK)],
    ]
    failed_files: list[str] = []
    outputs: list[str] = []
    for repo_root, files in sorted(targets_by_repo.items()):
        for check in checks:
            result = subprocess.run(  # noqa: S603  # trusted local linters
                [*check, *files],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == VIOLATIONS_FOUND:
                failed_files.extend(files)
                outputs.append((result.stdout + "\n" + result.stderr).strip())
    return failed_files, outputs


def main() -> None:
    """Read completion payload from stdin and enforce strict linting."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        print("{}")
        sys.exit(0)

    if payload.get("status") != "completed":
        print("{}")
        sys.exit(0)

    workspace_dir = _find_workspace_root(payload)
    git_root = _get_git_root(workspace_dir)

    targets_by_repo = _collect_target_files(payload, git_root)
    if not targets_by_repo:
        _cleanup_turn_records(payload, clear_pending=True)
        print("{}")
        sys.exit(0)

    uvx_bin = shutil.which("uvx")
    if not uvx_bin or not RUFF_CONFIG.is_file() or not DOCSTRING_CHECK.is_file():
        sys.stderr.write(
            f"verify_python_lint: skipped, uvx or {STYLEGUIDE_DIR} missing\n"
        )
        print("{}")
        sys.exit(0)

    failed_files, outputs = _run_checks_by_repo(uvx_bin, targets_by_repo)
    if failed_files:
        _save_pending_records(payload, sorted(set(failed_files)))
        _cleanup_turn_records(payload, clear_pending=False)
        output = "\n\n".join(outputs)
        followup = (
            "Strict Python lint (agent-dev-harness `ruff-base.toml` and "
            "`docstring_length.py`) found issues in changed files.\n"
            f"Run `uvx ruff@{RUFF_VERSION} check --config {RUFF_CONFIG} --fix <files>` "
            "for safe fixes and correct the remaining violations:\n\n"
            f"{output}"
        )
        print(json.dumps({"followup_message": followup}))
        sys.exit(0)

    _cleanup_turn_records(payload, clear_pending=True)
    print("{}")
    sys.exit(0)


if __name__ == "__main__":
    main()
