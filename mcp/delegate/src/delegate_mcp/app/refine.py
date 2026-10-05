from delegate_mcp.app.context import AppContext
from delegate_mcp.core import prompts
from delegate_mcp.core.formatting import format_response
from delegate_mcp.infra.delegation_log import log_delegation
from delegate_mcp.models import RefineRequest, ResponseReport, Verification, WorkerRun


def refine_delegation(ctx: AppContext, request: RefineRequest) -> str:
    """Send corrections into an earlier conversation, then re-check when asked to."""
    work_dir = request.working_directory or str(ctx.settings.dev_path)
    verify_dir = request.verify_directory or work_dir
    res = ctx.runner.run(
        WorkerRun(
            prompt=prompts.refine_prompt(
                request.feedback,
                request.verify_command,
                verify_dir,
                ctx.settings.max_verify_rounds,
            ),
            working_directory=work_dir,
            timeout_seconds=request.timeout_seconds,
            target_file=request.target_file or None,
            conversation_id=request.conversation_id,
            model=request.model,
            effort=request.effort,
        )
    )

    verification: Verification | None = None
    if request.verify_command:
        verification = ctx.verifier.run(
            command=prompts.verify_command_line(request.verify_command, verify_dir),
            working_directory=verify_dir,
            timeout_seconds=ctx.settings.verify_timeout_seconds,
        )

    log_delegation(
        ctx.settings.log_path,
        "refine_delegation",
        res,
        verified=verification.passed if verification else None,
        refine_of=request.conversation_id,
    )
    return format_response(
        ResponseReport(
            title="Refinement",
            result=res,
            review_steps=[
                "Re-read only the parts you asked it to change.",
                "Confirm the correction landed and nothing else regressed.",
            ],
            target_file=request.target_file or None,
            verification=verification,
        )
    )
