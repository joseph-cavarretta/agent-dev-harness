from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0


class ExecutionResult(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    command: List[str]
    target_file: Optional[str] = None
    conversation_id: Optional[str] = None
    duration_seconds: Optional[float] = None
    usage: Optional[Usage] = None
    structured_output: Optional[Dict[str, Any]] = None


class Verification(BaseModel):
    """Result of the server running a verify command itself, not agy's claim about it."""

    command: str
    passed: bool
    exit_code: int
    output: str
