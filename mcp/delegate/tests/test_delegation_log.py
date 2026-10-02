import json
from pathlib import Path
from delegate_mcp.delegation_log import log_delegation
from delegate_mcp.models import ExecutionResult, Usage


def test_log_delegation_appends_a_row(tmp_path) -> None:
    log = tmp_path / "nested" / "log.jsonl"
    res = ExecutionResult(
        success=True, stdout="", stderr="", exit_code=0, command=["worker"],
        target_file="/tmp/x.py", conversation_id="c1", duration_seconds=3.14,
        usage=Usage(input_tokens=10, output_tokens=2, cache_read_tokens=5),
    )
    log_delegation(log, "delegate_code_draft", res, verified=True, refine_of="c0")

    row = json.loads(log.read_text(encoding="utf-8").strip())
    assert row["tool"] == "delegate_code_draft"
    assert row["verified"] is True
    assert row["refine_of"] == "c0"
    assert row["duration_s"] == 3.1
    assert row["cached_tokens"] == 5


def test_log_delegation_never_raises_on_a_bad_path() -> None:
    res = ExecutionResult(success=True, stdout="", stderr="", exit_code=0, command=[])
    log_delegation(Path("/proc/nope/cannot-write.jsonl"), "delegate_task", res)
