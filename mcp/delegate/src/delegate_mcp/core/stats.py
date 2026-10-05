from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from delegate_mcp.models import LogEntry


def _verification_lines(recent: Sequence[LogEntry]) -> list[str]:
    """How often an independent check ran, passed, and disagreed with the worker."""
    checked = [e for e in recent if e.verified is not None]
    if not checked:
        return [
            "Nothing was independently verified. Pass verify_command so a pass is "
            "observed."
        ]
    verified_ok = sum(1 for e in checked if e.verified)
    disagreed = sum(1 for e in checked if bool(e.verified) != e.worker_succeeded)
    return [
        f"Independently verified: {verified_ok}/{len(checked)} passed",
        f"The worker's status disagreed with the check {disagreed} time(s)"
        " — a reminder not to trust its self-report",
    ]


def summarize(entries: Sequence[LogEntry], limit: int, log_path: Path) -> str:
    """Report on the last `limit` delegations: correction rate, verification, cost."""
    recent = entries[-limit:]
    total = len(recent)
    refines = sum(1 for e in recent if e.refine_of)
    first_attempts = total - refines
    worker_ok = sum(1 for e in recent if e.worker_succeeded)
    tokens_in = sum(e.input_tokens or 0 for e in recent)
    tokens_out = sum(e.output_tokens or 0 for e in recent)
    cached = sum(e.cached_tokens or 0 for e in recent)
    seconds = sum(e.duration_s or 0 for e in recent)
    by_tool = Counter(str(e.tool) for e in recent)

    lines = [
        f"=== Delegation stats (last {total} of {len(entries)}) ===",
        f"Log: {log_path}",
        "",
        f"First attempts: {first_attempts} · corrections sent back: {refines}",
    ]
    if first_attempts:
        lines.append(
            f"Correction rate: {refines / first_attempts:.0%} of first attempts "
            "needed a refine"
        )
    lines.append(f"Worker reported success: {worker_ok}/{total}")
    lines.extend(_verification_lines(recent))
    lines.extend(
        [
            "",
            f"Worker tokens: {tokens_in:,} in / {tokens_out:,} out ({cached:,} cached)",
            f"Worker wall-clock: {seconds / 60:.0f} min",
            "",
            "By tool: " + ", ".join(f"{k}={v}" for k, v in sorted(by_tool.items())),
            "",
            "Compare against what these drafts would have cost you to write directly."
            " A delegation that needed several corrections was probably a loss.",
        ]
    )
    return "\n".join(lines)
