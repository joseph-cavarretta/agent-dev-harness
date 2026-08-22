from typing import Any, Dict, List, Optional, Protocol
from antigravity_mcp.models import ExecutionResult, Verification


class AgyRunnerProtocol(Protocol):
    def run_prompt(
        self,
        prompt: str,
        working_directory: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        additional_dirs: Optional[List[str]] = None,
        target_file: Optional[str] = None,
        conversation_id: Optional[str] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult: ...


class CommandVerifierProtocol(Protocol):
    def run(
        self,
        command: str,
        working_directory: str,
        timeout_seconds: int,
    ) -> Verification: ...
