from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict

Effort: TypeAlias = Literal["low", "medium", "high"]
# JSON objects pass through from the worker and from tool callers unchanged; their
# shape is whatever the caller's schema says, so there is nothing narrower to name.
JsonObject: TypeAlias = dict[str, Any]

_VALUE = ConfigDict(strict=True, extra="forbid", frozen=True)


class Usage(BaseModel):
    """Token counts the worker reports for one run."""

    # The worker adds new counters over time; unknown ones are ignored, not rejected.
    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0


class ExecutionResult(BaseModel):
    """What one worker run produced, as observed by this server."""

    model_config = _VALUE

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    command: list[str]
    target_file: str | None = None
    conversation_id: str | None = None
    duration_seconds: float | None = None
    usage: Usage | None = None
    structured_output: JsonObject | None = None


class Verification(BaseModel):
    """Result of the server running a verify command itself, not the worker's claim."""

    model_config = _VALUE

    command: str
    passed: bool
    exit_code: int
    output: str


class WorkerRun(BaseModel):
    """One prompt for the worker plus where and how to run it."""

    model_config = _VALUE

    prompt: str
    working_directory: str | None = None
    timeout_seconds: int | None = None
    additional_dirs: list[str] | None = None
    target_file: str | None = None
    conversation_id: str | None = None
    model: str | None = None
    effort: str | None = None
    output_schema: JsonObject | None = None


class TaskRequest(BaseModel):
    """Arguments of delegate_task."""

    model_config = _VALUE

    instruction: str
    working_directory: str = ""
    output_schema: JsonObject | None = None
    timeout_seconds: int = 300
    additional_dirs: list[str] | None = None
    conversation_id: str = ""
    model: str | None = None
    effort: Effort | None = None


class CodeDraftRequest(BaseModel):
    """Arguments of delegate_code_draft."""

    model_config = _VALUE

    target_file: str
    task_description: str
    verify_command: str = ""
    verify_directory: str = ""
    context_files: list[str] | None = None
    conversation_id: str = ""
    model: str | None = None
    effort: Effort | None = None


class VaultDocumentRequest(BaseModel):
    """Arguments of delegate_vault_document."""

    model_config = _VALUE

    relative_path: str
    topic: str
    source_context: str
    template_name: str = ""
    model: str | None = None
    effort: Effort | None = None


class RefineRequest(BaseModel):
    """Arguments of refine_delegation."""

    model_config = _VALUE

    conversation_id: str
    feedback: str
    working_directory: str = ""
    target_file: str = ""
    verify_command: str = ""
    verify_directory: str = ""
    timeout_seconds: int = 300
    model: str | None = None
    effort: Effort | None = None


class LogEntry(BaseModel):
    """One line of the delegation log.

    Logs written before the worker rename carry `agy_reported_success` instead of
    `worker_reported_success`; both are read so old entries still count.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    tool: str | None = None
    worker_reported_success: bool | None = None
    agy_reported_success: bool | None = None
    verified: bool | None = None
    refine_of: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    duration_s: float | None = None

    @property
    def worker_succeeded(self) -> bool:
        """The worker's own success claim, from whichever key this entry uses."""
        if self.worker_reported_success is not None:
            return self.worker_reported_success
        return bool(self.agy_reported_success)


class ResponseReport(BaseModel):
    """Everything that goes into the text a delegation tool returns."""

    model_config = _VALUE

    title: str
    result: ExecutionResult
    review_steps: list[str]
    target_file: str | None = None
    notes: list[str] = []
    verification: Verification | None = None
