#!/usr/bin/env python3
"""Cursor stop hook to gate completion on technical documentation linting.

Verifies only markdown files touched by the agent during the active
turn or task using vale-lint. If violations are found, returns a followup
message to prompt agent remediation.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# directories and files skipped by default (templates, logs, agent prompts, envs)
SKIP_PATTERN = re.compile(
    r"(^|/)(?:"
    r"(?:\.obsidian|_templates|\.local|\.claude|\.cursor|\.worktrees|worktrees|\.venv|venv|node_modules|raw|archive|\.github)/"
    r"|(?:INDEX|log|CHANGELOG|CLAUDE(?:\.[A-Za-z0-9_-]+)?|AGENTS|SKILL)\.md$"
    r")"
)
WORKTREE_ROOT_PATTERN = re.compile(r"^.*?/(?:\.(?:cursor|claude)/)?\.?worktrees/[^/]+/")
TRACK_DIR = Path.home() / ".cursor/var/agent-edits"


def _is_skipped_path(path_str: str) -> bool:
    """Check whether a file path should be skipped after stripping any worktree root."""
    normalized = WORKTREE_ROOT_PATTERN.sub("/", path_str)
    return bool(SKIP_PATTERN.search(normalized))


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


def _read_tracked_paths(file_path: Path) -> set[str]:
    """Read recorded markdown file paths from a tracking log."""
    paths: set[str] = set()
    if not file_path.is_file():
        return paths
    try:
        for line in file_path.read_text(encoding="utf-8").splitlines():
            cleaned = line.strip()
            if cleaned.endswith((".md", ".mdx")):
                paths.add(cleaned)
    except OSError:
        pass
    return paths


def _collect_target_files(
    payload: dict[str, object], git_root: Path | None
) -> list[str]:
    """Collect markdown files edited by the agent during this turn or task."""
    candidates: set[str] = set()

    # subagentstop payload includes modified_files
    raw_modified = payload.get("modified_files")
    if isinstance(raw_modified, list):
        candidates.update(
            item
            for item in raw_modified
            if isinstance(item, str) and item.endswith((".md", ".mdx"))
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
        candidates.update(_read_tracked_paths(TRACK_DIR / f"{conv_id}_pending_md.txt"))

    valid_files: list[str] = []
    for candidate in sorted(candidates):
        path_obj = Path(candidate)
        if not path_obj.is_absolute() and git_root:
            path_obj = git_root / path_obj
        resolved = path_obj.resolve()
        if resolved.is_file() and not _is_skipped_path(str(resolved)):
            valid_files.append(str(resolved))

    return valid_files


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
    """Remove markdown tracking records for this turn."""
    gen_id = payload.get("generation_id")
    conv_id = payload.get("conversation_id") or payload.get("session_id")
    if isinstance(gen_id, str) and gen_id:
        _strip_extensions_from_log(TRACK_DIR / f"{gen_id}.txt", (".md", ".mdx"))
    if clear_pending and isinstance(conv_id, str) and conv_id:
        (TRACK_DIR / f"{conv_id}_pending_md.txt").unlink(missing_ok=True)


def _save_pending_records(
    payload: dict[str, object], files: list[str]
) -> None:
    """Save pending files to verify on subsequent remediation loops."""
    conv_id = payload.get("conversation_id") or payload.get("session_id")
    if not isinstance(conv_id, str) or not conv_id:
        return
    pending_file = TRACK_DIR / f"{conv_id}_pending_md.txt"
    try:
        TRACK_DIR.mkdir(parents=True, exist_ok=True)
        pending_file.write_text("\n".join(files) + "\n", encoding="utf-8")
    except OSError:
        pass


def main() -> None:
    """Read completion payload from stdin and enforce prose linting."""
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

    target_files = _collect_target_files(payload, git_root)
    if not target_files:
        _cleanup_turn_records(payload, clear_pending=True)
        print("{}")
        sys.exit(0)

    linter_bin = shutil.which("vale-lint")
    if not linter_bin:
        print("{}")
        sys.exit(0)

    working_dir = git_root or workspace_dir
    result = subprocess.run(  # noqa: S603  # trusted local linter binary
        [linter_bin, *target_files],
        cwd=working_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        _save_pending_records(payload, target_files)
        _cleanup_turn_records(payload, clear_pending=False)
        output = (result.stdout + "\n" + result.stderr).strip()
        followup = (
            "Prose linter (`vale-lint`) found style issues in changed Markdown files.\n"
            "Follow Google Technical Writing style (second person / imperative, "
            "sentence-case headings, no editorial 'we') and resolve the violations:\n\n"
            f"{output}"
        )
        print(json.dumps({"followup_message": followup}))
        sys.exit(0)

    _cleanup_turn_records(payload, clear_pending=True)
    print("{}")
    sys.exit(0)


if __name__ == "__main__":
    main()
