from delegate_mcp.config import Settings
from delegate_mcp.protocols import CommandVerifierProtocol, WorkerRunnerProtocol

STANDARDS_CHECK = (
    "Check the standards: Pydantic models, Protocols for DI, BaseSettings, no"
    " os.environ, no lazy imports."
)


class AppContext:
    """The dependencies every delegation use case shares."""

    def __init__(
        self,
        settings: Settings,
        runner: WorkerRunnerProtocol,
        verifier: CommandVerifierProtocol,
    ) -> None:
        self.settings = settings
        self.runner = runner
        self.verifier = verifier
