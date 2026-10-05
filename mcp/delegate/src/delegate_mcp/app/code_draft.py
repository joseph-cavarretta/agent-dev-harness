from pathlib import Path

from delegate_mcp.app.context import STANDARDS_CHECK, AppContext
from delegate_mcp.core import prompts
from delegate_mcp.core.formatting import format_response
from delegate_mcp.infra.delegation_log import log_delegation
from delegate_mcp.models import (
    CodeDraftRequest,
    ExecutionResult,
    ResponseReport,
    Verification,
    WorkerRun,
)


class _DraftJob:
    """Where one code draft runs and is checked, worked out from its request."""

    def __init__(self, ctx: AppContext, request: CodeDraftRequest) -> None:
        self.request = request
        self.dest_path = Path(request.target_file)
        paths = [Path(p) for p in request.context_files or []]
        self.missing = [str(p) for p in paths if not p.exists()]
        self.present = [p for p in paths if p.exists()]
        parent = self.dest_path.parent
        self.work_dir = str(parent if parent.exists() else ctx.settings.dev_path)
        self.verify_dir = request.verify_directory or self.work_dir

    def extra_dirs(self) -> list[str] | None:
        """Context and verify directories outside the working directory, if any."""
        dirs = {str(p.parent) for p in self.present if str(p.parent) != self.work_dir}
        if self.verify_dir != self.work_dir:
            dirs.add(self.verify_dir)
        return sorted(dirs) or None

    def run(
        self, ctx: AppContext, prompt: str, conversation_id: str | None
    ) -> WorkerRun:
        """A worker run for this draft with the given prompt."""
        return WorkerRun(
            prompt=prompt,
            working_directory=self.work_dir,
            timeout_seconds=ctx.settings.default_timeout_seconds,
            target_file=str(self.dest_path),
            conversation_id=conversation_id,
            model=self.request.model,
            effort=self.request.effort,
        )


def _check(ctx: AppContext, job: _DraftJob) -> Verification:
    """Run the verify command here, where the result is actually observed."""
    return ctx.verifier.run(
        command=prompts.verify_command_line(job.request.verify_command, job.verify_dir),
        working_directory=job.verify_dir,
        timeout_seconds=ctx.settings.verify_timeout_seconds,
    )


def _verify_until_passing(
    ctx: AppContext, job: _DraftJob, res: ExecutionResult
) -> tuple[ExecutionResult, Verification, int]:
    """Check the draft, sending real failures back until it passes or rounds run out.

    The retry loop lives here, not in the worker's head: its shell may start in a
    scratch directory and it will report a passing run it never made. Only this side
    sees the real result, so only this side can decide whether to iterate.
    """
    verification = _check(ctx, job)
    rounds = 1
    while (
        not verification.passed
        and rounds < ctx.settings.max_verify_rounds
        and res.conversation_id
    ):
        retry = prompts.verify_retry(
            job.request.verify_command, job.verify_dir, rounds, verification.output
        )
        res = ctx.runner.run(job.run(ctx, retry, res.conversation_id))
        verification = _check(ctx, job)
        rounds += 1
    return res, verification, rounds


def delegate_code_draft(ctx: AppContext, request: CodeDraftRequest) -> str:
    """Have the worker write one file, then prove it with the verify command."""
    job = _DraftJob(ctx, request)
    notes: list[str] = []
    if job.missing:
        notes.append(f"Context files not found and skipped: {', '.join(job.missing)}")

    prompt = prompts.code_draft_prompt(
        job.dest_path,
        request.task_description,
        job.present,
        request.verify_command,
        job.verify_dir,
        ctx.settings.max_verify_rounds,
    )
    if not request.verify_command:
        notes.append(
            "No verify_command given, so nothing proves this works. Prefer supplying one."
        )
    first = job.run(ctx, prompt, request.conversation_id or None)
    res = ctx.runner.run(first.model_copy(update={"additional_dirs": job.extra_dirs()}))

    verification: Verification | None = None
    rounds = 0
    if request.verify_command:
        res, verification, rounds = _verify_until_passing(ctx, job, res)
        notes.append(
            f"Verify rounds: {rounds}"
            + ("" if verification.passed else f" (gave up after {rounds})")
        )

    log_delegation(
        ctx.settings.log_path,
        "delegate_code_draft",
        res,
        verified=verification.passed if verification else None,
        verify_rounds=rounds or None,
    )
    if verification and verification.passed:
        review = [
            "The check passes, so behavior is proven — read the diff for design, not "
            "for bugs.",
            "Confirm the check actually covers the specification's edge cases.",
            STANDARDS_CHECK,
        ]
    else:
        review = [
            f"Read {job.dest_path} in full — nothing proves this works.",
            STANDARDS_CHECK,
            "Run the tests yourself.",
        ]
    return format_response(
        ResponseReport(
            title="Code Draft Delegation",
            result=res,
            review_steps=review,
            target_file=str(job.dest_path),
            notes=notes,
            verification=verification,
        )
    )
