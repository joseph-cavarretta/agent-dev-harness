import json
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from antigravity_mcp.config import Settings
from antigravity_mcp.models import ExecutionResult, Usage
from antigravity_mcp.protocols import AgyRunnerProtocol


def _parse_agy_json(stdout: str) -> Optional[Dict[str, Any]]:
    """Pull the result object out of `agy --output-format json` output.

    agy normally prints one JSON object, but tolerate leading log lines by scanning
    backwards for the last line that parses as an object.
    """
    text = stdout.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


class AgyRunner(AgyRunnerProtocol):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run_prompt(
        self,
        prompt: str,
        working_directory: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        additional_dirs: Optional[List[str]] = None,
        target_file: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> ExecutionResult:
        cwd = Path(working_directory) if working_directory else self.settings.dev_path
        print_timeout = timeout_seconds or self.settings.default_timeout_seconds
        # agy enforces its own --print-timeout. Give the subprocess a longer leash so agy
        # times out first and we keep its error message instead of killing it blind.
        subprocess_timeout = print_timeout + self.settings.timeout_grace_seconds

        cmd: List[str] = [
            str(self.settings.agy_bin_path),
            "--print",
            prompt,
            "--model",
            self.settings.default_model,
            "--effort",
            self.settings.default_effort,
            "--output-format",
            "json",
            "--print-timeout",
            f"{print_timeout}s",
        ]

        if conversation_id:
            cmd.extend(["--conversation", conversation_id])

        if self.settings.dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")

        for extra_dir in additional_dirs or []:
            cmd.extend(["--add-dir", extra_dir])

        started = time.monotonic()
        try:
            res = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=subprocess_timeout,
            )
        except subprocess.TimeoutExpired as e:
            stdout_text = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            return ExecutionResult(
                success=False,
                stdout=stdout_text,
                stderr=(
                    f"agy did not exit within {subprocess_timeout}s "
                    f"(--print-timeout was {print_timeout}s)"
                ),
                exit_code=-1,
                command=cmd,
                target_file=target_file,
            )
        except OSError as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Could not run {self.settings.agy_bin_path}: {e}",
                exit_code=-1,
                command=cmd,
                target_file=target_file,
            )

        # agy's own duration_seconds is not wall clock (a 21s run reported 1.7), so measure it here.
        elapsed = time.monotonic() - started

        payload = _parse_agy_json(res.stdout)
        if payload is None:
            return ExecutionResult(
                success=(res.returncode == 0),
                stdout=res.stdout,
                stderr=res.stderr,
                exit_code=res.returncode,
                command=cmd,
                target_file=target_file,
                duration_seconds=elapsed,
            )

        status = str(payload.get("status", "")).upper()
        usage_data = payload.get("usage")
        return ExecutionResult(
            success=(res.returncode == 0 and status in ("", "SUCCESS")),
            stdout=payload.get("response", ""),
            stderr=res.stderr or (payload.get("error") or ""),
            exit_code=res.returncode,
            command=cmd,
            target_file=target_file,
            conversation_id=payload.get("conversation_id"),
            duration_seconds=elapsed,
            usage=Usage(**usage_data) if isinstance(usage_data, dict) else None,
        )
