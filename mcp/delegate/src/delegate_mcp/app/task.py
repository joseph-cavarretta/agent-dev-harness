from delegate_mcp.app.context import AppContext
from delegate_mcp.core.formatting import format_response
from delegate_mcp.infra.delegation_log import log_delegation
from delegate_mcp.models import ResponseReport, TaskRequest, WorkerRun

_STRUCTURED_REVIEW = [
    "The structured output is schema-valid, but the facts in it are not verified —"
    " spot-check anything load-bearing against the source.",
    "Inspect any file the worker created or changed.",
]
_PROSE_REVIEW = [
    "Check the output for accuracy, consistency, and gaps.",
    "Inspect any file it created or changed with Read or Grep.",
    "If it wrote code, run the tests.",
]


def delegate_task(ctx: AppContext, request: TaskRequest) -> str:
    """Run a free-form instruction through the worker and report the result."""
    work_dir = request.working_directory or str(ctx.settings.dev_path)
    res = ctx.runner.run(
        WorkerRun(
            prompt=request.instruction,
            working_directory=work_dir,
            timeout_seconds=request.timeout_seconds,
            additional_dirs=request.additional_dirs,
            conversation_id=request.conversation_id or None,
            model=request.model,
            effort=request.effort,
            output_schema=request.output_schema,
        )
    )
    log_delegation(ctx.settings.log_path, "delegate_task", res)
    review = _STRUCTURED_REVIEW if res.structured_output is not None else _PROSE_REVIEW
    return format_response(
        ResponseReport(
            title="Delegated Task",
            result=res,
            review_steps=review,
            notes=[f"Working directory: {work_dir}"],
        )
    )
