from typing import List, Optional, Protocol
from antigravity_mcp.models import ExecutionResult


class AgyRunnerProtocol(Protocol):
    def run_prompt(
        self,
        prompt: str,
        working_directory: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        additional_dirs: Optional[List[str]] = None,
        target_file: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> ExecutionResult: ...
