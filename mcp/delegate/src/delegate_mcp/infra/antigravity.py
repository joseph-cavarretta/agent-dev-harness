import json
import subprocess
import time
from pathlib import Path

from delegate_mcp.config import Settings
from delegate_mcp.models import ExecutionResult, JsonObject, Usage, WorkerRun

VALID_EFFORTS = ("low", "medium", "high")


def _as_object(text: str) -> JsonObject | None:
    """Text parsed as JSON when it is an object, else None."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_json_output(stdout: str) -> JsonObject | None:
    """Pull the result object out of `agy --output-format json` output.

    agy normally prints one JSON object, but tolerate leading log lines by scanning
    backwards for the last line that parses as an object.
    """
    text = stdout.strip()
    if not text:
        return None
    whole = _as_object(text)
    if whole is not None:
        return whole
    for raw in reversed(text.splitlines()):
        line = raw.strip()
        if line.startswith("{"):
            parsed = _as_object(line)
            if parsed is not None:
                return parsed
    return None


def _result_from_payload(
    payload: JsonObject,
    res: subprocess.CompletedProcess[str],
    job: WorkerRun,
    cmd: list[str],
) -> ExecutionResult:
    """ExecutionResult for a run whose stdout held agy's JSON result object."""
    status = str(payload.get("status", "")).upper()
    usage_data = payload.get("usage")
    structured = payload.get("structured_output")
    return ExecutionResult(
        success=(res.returncode == 0 and status in ("", "SUCCESS")),
        stdout=payload.get("response", ""),
        stderr=res.stderr or (payload.get("error") or ""),
        exit_code=res.returncode,
        command=cmd,
        target_file=job.target_file,
        conversation_id=payload.get("conversation_id"),
        usage=Usage.model_validate(usage_data)
        if isinstance(usage_data, dict)
        else None,
        structured_output=structured if isinstance(structured, dict) else None,
    )


class AntigravityRunner:
    """Runs the Antigravity CLI (`agy`) as the worker."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _command(self, job: WorkerRun, effort: str, print_timeout: int) -> list[str]:
        """The agy argv for a job."""
        cmd = [
            str(self.settings.worker_bin_path),
            "--print",
            job.prompt,
            "--model",
            job.model or self.settings.default_model,
            "--effort",
            effort,
            "--output-format",
            "json",
            "--print-timeout",
            f"{print_timeout}s",
        ]
        if job.output_schema:
            cmd.extend(["--json-schema", json.dumps(job.output_schema)])
        if job.conversation_id:
            cmd.extend(["--conversation", job.conversation_id])
        if self.settings.dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")
        for extra_dir in job.additional_dirs or []:
            cmd.extend(["--add-dir", extra_dir])
        return cmd

    def run(self, job: WorkerRun) -> ExecutionResult:
        """Run the job through agy; failures come back as an unsuccessful result."""
        cwd = Path(job.working_directory or self.settings.dev_path)
        print_timeout = job.timeout_seconds or self.settings.default_timeout_seconds
        # agy enforces its own --print-timeout. Give the subprocess a longer leash so
        # agy times out first and we keep its error message instead of killing it blind.
        subprocess_timeout = print_timeout + self.settings.timeout_grace_seconds

        effort = (job.effort or self.settings.default_effort).lower()
        if effort not in VALID_EFFORTS:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=(
                    f"effort must be one of {', '.join(VALID_EFFORTS)}, got {effort!r}"
                ),
                exit_code=-1,
                command=[],
                target_file=job.target_file,
            )

        cmd = self._command(job, effort, print_timeout)
        started = time.monotonic()
        try:
            res = subprocess.run(  # noqa: S603  # argv list built above, no shell
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=subprocess_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            partial = e.stdout
            return ExecutionResult(
                success=False,
                stdout=partial.decode()
                if isinstance(partial, bytes)
                else partial or "",
                stderr=(
                    f"agy did not exit within {subprocess_timeout}s "
                    f"(--print-timeout was {print_timeout}s)"
                ),
                exit_code=-1,
                command=cmd,
                target_file=job.target_file,
                duration_seconds=time.monotonic() - started,
            )
        except OSError as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Could not run {self.settings.worker_bin_path}: {e}",
                exit_code=-1,
                command=cmd,
                target_file=job.target_file,
            )

        # agy's own duration_seconds is not wall clock (a 21s run reported 1.7), so
        # measure here.
        elapsed = time.monotonic() - started
        payload = parse_json_output(res.stdout)
        if payload is None:
            return ExecutionResult(
                success=(res.returncode == 0),
                stdout=res.stdout,
                stderr=res.stderr,
                exit_code=res.returncode,
                command=cmd,
                target_file=job.target_file,
                duration_seconds=elapsed,
            )
        return _result_from_payload(payload, res, job, cmd).model_copy(
            update={"duration_seconds": elapsed}
        )
