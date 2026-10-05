import json

from delegate_mcp.models import ExecutionResult, ResponseReport, Verification


def usage_line(res: ExecutionResult) -> str | None:
    """One line of token and time spend, or None when the worker reported no usage."""
    if res.usage is None:
        return None
    u = res.usage
    line = f"Delegated to worker: {u.input_tokens:,} in / {u.output_tokens:,} out"
    if u.cache_read_tokens:
        line += f" ({u.cache_read_tokens:,} cached)"
    if res.duration_seconds:
        line += f" · {res.duration_seconds:.0f}s"
    return line


def _verification_lines(verification: Verification, res: ExecutionResult) -> list[str]:
    """The server's own check, plus a note when the worker's claim disagrees with it."""
    verdict = "passed" if verification.passed else "FAILED"
    lines = [
        "",
        "--- Verification (run by this server, not the worker) ---",
        f"$ {verification.command}",
        f"exit {verification.exit_code} — {verdict}",
        verification.output,
    ]
    if verification.passed and not res.success:
        lines.append(
            "(The worker reported a failure but the check passes. Its status is "
            "unreliable; the check is the evidence.)"
        )
    elif not verification.passed and res.success:
        lines.append(
            "(The worker claimed success. The check disagrees. Trust the check.)"
        )
    return lines


def _failure_lines(report: ResponseReport) -> list[str]:
    """Error output and retry advice for a delegation that did not succeed."""
    res = report.result
    lines: list[str] = []
    if report.verification is None:
        lines.extend(["--- Error ---", res.stderr or "(no error output)"])
    if res.stdout:
        lines.extend(["", "--- Worker output ---", res.stdout])
    lines.extend(
        [
            "",
            "Diagnose the actual failure before retrying. If the draft is close, send"
            " corrections with refine_delegation rather than starting over.",
        ]
    )
    if res.conversation_id:
        lines.append(f"conversation_id: {res.conversation_id}")
    return lines


def _success_lines(report: ResponseReport) -> list[str]:
    """Worker output and the review checklist for a delegation that succeeded."""
    res = report.result
    lines = ["--- Output ---", res.stdout or "(written to file, no summary returned)"]
    if res.structured_output is not None:
        lines.extend(
            [
                "",
                "--- Structured output (schema-validated) ---",
                json.dumps(res.structured_output, indent=2),
            ]
        )
    lines.extend(["", "=== Review before calling this done ==="])
    lines.extend(f"{i}. {step}" for i, step in enumerate(report.review_steps, start=1))
    if res.conversation_id:
        lines.extend(
            [
                "",
                "To correct the draft, send the fixes back with "
                f"refine_delegation(conversation_id='{res.conversation_id}', ...).",
                "The worker still holds this context, so a correction costs far less "
                "than rewriting the file yourself.",
            ]
        )
    return lines


def format_response(report: ResponseReport) -> str:
    """The text a delegation tool returns to the calling agent.

    When a verify command ran, the observed result decides success, not the worker's
    self-report: the worker has been seen reporting ERROR on a run that passed and
    SUCCESS on one that failed.
    """
    res, verification = report.result, report.verification
    done = verification.passed if verification is not None else res.success
    state = "PASSED" if done else "FAILED"
    if verification is None and not res.success:
        state += f" (exit code {res.exit_code})"

    lines = [f"=== {report.title}: {state} ==="]
    if report.target_file:
        lines.append(f"Target file: {report.target_file}")
    usage = usage_line(res)
    if usage:
        lines.append(usage)
    lines.extend(f"Note: {note}" for note in report.notes)
    if verification is not None:
        lines.extend(_verification_lines(verification, res))
    lines.append("")
    lines.extend(_success_lines(report) if done else _failure_lines(report))
    return "\n".join(lines)
