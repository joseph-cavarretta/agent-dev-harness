from typing import List, Optional
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
