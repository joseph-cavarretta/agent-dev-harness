import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from delegate_mcp.models import ExecutionResult


def log_delegation(
    log_path: Path,
    tool: str,
    result: ExecutionResult,
    verified: Optional[bool] = None,
    refine_of: Optional[str] = None,
    verify_rounds: Optional[int] = None,
) -> None:
    """Append one line per delegation so the accept rate can be measured later.

    Never let bookkeeping break a delegation.
    """
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": tool,
        "target": result.target_file,
        "worker_reported_success": result.success,
        "verified": verified,
        "verify_rounds": verify_rounds,
        "refine_of": refine_of,
        "conversation_id": result.conversation_id,
        "duration_s": round(result.duration_seconds, 1) if result.duration_seconds else None,
        "input_tokens": result.usage.input_tokens if result.usage else None,
        "output_tokens": result.usage.output_tokens if result.usage else None,
        "cached_tokens": result.usage.cache_read_tokens if result.usage else None,
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass
