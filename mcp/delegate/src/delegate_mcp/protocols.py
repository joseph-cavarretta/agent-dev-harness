from typing import Protocol

from delegate_mcp.models import ExecutionResult, Verification, WorkerRun


class WorkerRunnerProtocol(Protocol):
    """Runs one prompt through a worker agent."""

    def run(self, job: WorkerRun) -> ExecutionResult:
        """Run the job and report what was observed; never raises for worker failure."""
        ...


class CommandVerifierProtocol(Protocol):
    """Runs a verify command so a pass is observed rather than reported."""

    def run(
        self, command: str, working_directory: str, timeout_seconds: int
    ) -> Verification:
        """Run the command and report its exit status and output."""
        ...
