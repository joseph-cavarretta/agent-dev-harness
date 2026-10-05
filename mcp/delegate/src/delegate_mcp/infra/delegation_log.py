import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from delegate_mcp.models import ExecutionResult, LogEntry

logger = logging.getLogger(__name__)


def log_delegation(  # one keyword per logged column
    log_path: Path,
    tool: str,
    result: ExecutionResult,
    *,
    verified: bool | None = None,
    refine_of: str | None = None,
    verify_rounds: int | None = None,
) -> None:
    """Append one line per delegation so the accept rate can be measured later.

    Never lets bookkeeping break a delegation: a write failure is logged and dropped.
    """
    usage = result.usage
    entry = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "tool": tool,
        "target": result.target_file,
        "worker_reported_success": result.success,
        "verified": verified,
        "verify_rounds": verify_rounds,
        "refine_of": refine_of,
        "conversation_id": result.conversation_id,
        "duration_s": round(result.duration_seconds, 1)
        if result.duration_seconds
        else None,
        "input_tokens": usage.input_tokens if usage else None,
        "output_tokens": usage.output_tokens if usage else None,
        "cached_tokens": usage.cache_read_tokens if usage else None,
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        logger.warning("could not write delegation log at %s", log_path, exc_info=True)


def read_delegation_log(log_path: Path) -> list[LogEntry]:
    """Every readable entry in the log, oldest first; unparseable lines are skipped."""
    entries: list[LogEntry] = []
    for raw in log_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            entries.append(LogEntry.model_validate_json(line))
        except ValidationError:
            continue
    return entries
