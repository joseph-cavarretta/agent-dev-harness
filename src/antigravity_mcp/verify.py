import subprocess
from antigravity_mcp.models import Verification

MAX_OUTPUT_CHARS = 6000


def _tail(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return "...(truncated)...\n" + text[-MAX_OUTPUT_CHARS:]


class ShellVerifier:
    """Runs the verify command directly so a pass is observed, not reported.

    agy will claim success it does not have, so its word is never the evidence.
    """

    def run(self, command: str, working_directory: str, timeout_seconds: int) -> Verification:
        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=working_directory,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return Verification(
                command=command,
                passed=False,
                exit_code=-1,
                output=f"verify command did not finish within {timeout_seconds}s",
            )
        except OSError as e:
            return Verification(
                command=command,
                passed=False,
                exit_code=-1,
                output=f"could not run verify command: {e}",
            )

        combined = (res.stdout or "") + (res.stderr or "")
        return Verification(
            command=command,
            passed=(res.returncode == 0),
            exit_code=res.returncode,
            output=_tail(combined.strip()) or "(no output)",
        )
