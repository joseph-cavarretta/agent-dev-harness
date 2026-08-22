import json
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional
from mcp.server.mcpserver import MCPServer
from pydantic import Field
from antigravity_mcp import prompts
from antigravity_mcp.config import Settings
from antigravity_mcp.models import ExecutionResult, Verification
from antigravity_mcp.protocols import AgyRunnerProtocol, CommandVerifierProtocol
from antigravity_mcp.runner import AgyRunner, log_delegation
from antigravity_mcp.verify import ShellVerifier

TEMPLATE_BY_FOLDER = {
    "wiki/": "wiki",
    "investigations/": "investigation",
    "projects/": "project",
    "plans/": "plan-index",
    "meetings/": "meeting-one-on-one",
}

Effort = Literal["low", "medium", "high"]

MODEL_FIELD = Field(
    description=(
        "agy model id. Omit for the default (gemini-3.7-flash). Use a Pro model for genuinely "
        "hard reasoning; an unknown id is a hard error listing valid ones."
    )
)
EFFORT_FIELD = Field(
    description=(
        "Reasoning effort. Use 'low' for mechanical work, 'high' only when the task needs it. "
        "Omit for the configured default."
    )
)


def _usage_line(res: ExecutionResult) -> Optional[str]:
    if res.usage is None:
        return None
    u = res.usage
    line = f"Delegated to agy: {u.input_tokens:,} in / {u.output_tokens:,} out"
    if u.cache_read_tokens:
        line += f" ({u.cache_read_tokens:,} cached)"
    if res.duration_seconds:
        line += f" · {res.duration_seconds:.0f}s"
    return line


def _format_response(
    title: str,
    res: ExecutionResult,
    review_steps: List[str],
    target_file: Optional[str] = None,
    notes: Optional[List[str]] = None,
    verification: Optional[Verification] = None,
) -> str:
    # When a verify command ran, the observed result decides, not agy's self-report:
    # agy has been seen reporting ERROR on a run that passed and SUCCESS on one that failed.
    done = verification.passed if verification is not None else res.success
    state = "PASSED" if done else "FAILED"
    if verification is None:
        state += "" if res.success else f" (exit code {res.exit_code})"

    lines = [f"=== {title}: {state} ==="]
    if target_file:
        lines.append(f"Target file: {target_file}")
    usage = _usage_line(res)
    if usage:
        lines.append(usage)
    for note in notes or []:
        lines.append(f"Note: {note}")

    if verification is not None:
        lines.append("")
        lines.append(f"--- Verification (run by this server, not agy) ---")
        lines.append(f"$ {verification.command}")
        lines.append(f"exit {verification.exit_code} — {'passed' if verification.passed else 'FAILED'}")
        lines.append(verification.output)
        if verification.passed and not res.success:
            lines.append(
                "(agy reported a failure but the check passes. agy's status is unreliable; "
                "the check is the evidence.)"
            )
        elif not verification.passed and res.success:
            lines.append("(agy claimed success. The check disagrees. Trust the check.)")

    lines.append("")

    if not done:
        if verification is None:
            lines.extend(["--- Error ---", res.stderr or "(no error output)"])
        if res.stdout:
            lines.extend(["", "--- agy output ---", res.stdout])
        lines.extend(
            [
                "",
                "Diagnose the actual failure before retrying. If the draft is close, send"
                " corrections with refine_delegation rather than starting over.",
            ]
        )
        if res.conversation_id:
            lines.append(f"conversation_id: {res.conversation_id}")
        return "\n".join(lines)

    lines.extend(["--- Output ---", res.stdout or "(written to file, no summary returned)"])

    if res.structured_output is not None:
        lines.extend(
            ["", "--- Structured output (schema-validated) ---", json.dumps(res.structured_output, indent=2)]
        )

    lines.extend(["", "=== Review before calling this done ==="])
    lines.extend(f"{i}. {step}" for i, step in enumerate(review_steps, start=1))

    if res.conversation_id:
        lines.extend(
            [
                "",
                "To correct the draft, send the fixes back with "
                f"refine_delegation(conversation_id='{res.conversation_id}', ...).",
                "agy still holds this context, so a correction costs far less than rewriting"
                " the file yourself.",
            ]
        )
    return "\n".join(lines)


def create_server(
    settings: Optional[Settings] = None,
    runner: Optional[AgyRunnerProtocol] = None,
    verifier: Optional[CommandVerifierProtocol] = None,
) -> MCPServer:
    cfg = settings or Settings()
    exec_runner = runner or AgyRunner(cfg)
    exec_verifier = verifier or ShellVerifier()

    server = MCPServer("antigravity-worker")

    @server.tool()
    def delegate_task(
        instruction: Annotated[
            str,
            Field(
                description=(
                    "Self-contained instruction for agy. It has file read/write and terminal "
                    "tools and runs in working_directory, so name the paths it should read "
                    "instead of pasting their contents."
                )
            ),
        ],
        working_directory: Annotated[
            str,
            Field(description="Absolute path agy runs in. Defaults to ~/dev (all repos)."),
        ] = "",
        output_schema: Annotated[
            Optional[Dict[str, Any]],
            Field(
                description=(
                    "JSON Schema for the answer. Supply this whenever you will consume the "
                    "result rather than read prose: agy is forced to conform and the validated "
                    "object comes back separately from its chatter. Strongly preferred for "
                    "findings, extractions, and summaries."
                )
            ),
        ] = None,
        timeout_seconds: Annotated[
            int,
            Field(description="Wall-clock budget for agy. Raise it for multi-file work.", ge=30),
        ] = 300,
        additional_dirs: Annotated[
            Optional[List[str]],
            Field(description="Extra absolute paths to add to agy's workspace."),
        ] = None,
        conversation_id: Annotated[
            str,
            Field(
                description=(
                    "Continue an earlier delegation's conversation. Reuses its cached context, "
                    "so batching related work into one conversation is much cheaper than "
                    "separate cold calls."
                )
            ),
        ] = "",
        model: Annotated[Optional[str], MODEL_FIELD] = None,
        effort: Annotated[Optional[Effort], EFFORT_FIELD] = None,
    ) -> str:
        """Delegate bulk reading, searching, or summarizing to agy.

        This is the tool with the best economics: agy reads a lot and returns a little.
        Pass output_schema whenever you will act on the result programmatically.
        Do not use it for work smaller than the review it triggers.
        """
        work_dir = working_directory or str(cfg.dev_path)
        res = exec_runner.run_prompt(
            prompt=instruction,
            working_directory=work_dir,
            timeout_seconds=timeout_seconds,
            additional_dirs=additional_dirs,
            conversation_id=conversation_id or None,
            model=model,
            effort=effort,
            output_schema=output_schema,
        )
        log_delegation(cfg.log_path, "delegate_task", res)

        review = (
            [
                "The structured output is schema-valid, but the facts in it are not verified —"
                " spot-check anything load-bearing against the source.",
                "Inspect any file agy created or changed.",
            ]
            if res.structured_output is not None
            else [
                "Check the output for accuracy, consistency, and gaps.",
                "Inspect any file it created or changed with Read or Grep.",
                "If it wrote code, run the tests.",
            ]
        )
        return _format_response(
            "Antigravity Execution", res, review, notes=[f"Working directory: {work_dir}"]
        )

    @server.tool()
    def delegate_code_draft(
        target_file: Annotated[
            str, Field(description="Absolute path of the file agy should write.")
        ],
        task_description: Annotated[
            str,
            Field(description="What the code must do, including edge cases and expected behavior."),
        ],
        verify_command: Annotated[
            str,
            Field(
                description=(
                    "Shell command that proves the work is correct, e.g. 'uv run pytest "
                    "tests/test_worker.py -q'. agy iterates against it until it passes, then this "
                    "server re-runs it independently. Supply it whenever one exists — it is what "
                    "makes delegating cheaper than writing the code yourself."
                )
            ),
        ] = "",
        verify_directory: Annotated[
            str,
            Field(
                description=(
                    "Directory to run verify_command from, usually the repo root. Defaults to the "
                    "target file's parent."
                )
            ),
        ] = "",
        context_files: Annotated[
            Optional[List[str]],
            Field(
                description=(
                    "Absolute paths agy should read for context. Paths only — agy reads them "
                    "itself; do not paste file contents into task_description."
                )
            ),
        ] = None,
        conversation_id: Annotated[
            str,
            Field(
                description=(
                    "Continue an earlier conversation, for drafting several related files with "
                    "its context already warm."
                )
            ),
        ] = "",
        model: Annotated[Optional[str], MODEL_FIELD] = None,
        effort: Annotated[Optional[Effort], EFFORT_FIELD] = None,
    ) -> str:
        """Delegate drafting code or tests to agy, ideally against a command that proves it works.

        With verify_command the economics change: agy loops until the check passes and you
        review a green artifact instead of auditing prose. Without one, only delegate whole
        files — the review costs more than writing short code yourself.
        """
        dest_path = Path(target_file)
        paths = [Path(p) for p in context_files or []]
        missing = [str(p) for p in paths if not p.exists()]
        present = [p for p in paths if p.exists()]

        notes: List[str] = []
        if missing:
            notes.append(f"Context files not found and skipped: {', '.join(missing)}")

        work_dir = dest_path.parent if dest_path.parent.exists() else cfg.dev_path
        verify_dir = verify_directory or str(work_dir)

        prompt_parts = [
            f"Write or update the code in: {dest_path}",
            "",
            f"Specification: {task_description}",
            "",
            prompts.PYTHON_STANDARDS,
        ]

        if present:
            prompt_parts.extend(
                [
                    "",
                    "Read these files for context before writing. Match their conventions:",
                    *(f"- {p}" for p in present),
                ]
            )

        if verify_command:
            prompt_parts.extend(
                ["", prompts.verify_loop(verify_command, verify_dir, cfg.max_verify_rounds)]
            )
        else:
            prompt_parts.extend(["", f"Write the implementation into {dest_path} now."])
            notes.append(
                "No verify_command given, so nothing proves this works. Prefer supplying one."
            )

        extra_dirs = sorted({str(p.parent) for p in present if str(p.parent) != str(work_dir)})
        if verify_dir != str(work_dir):
            extra_dirs = sorted(set(extra_dirs) | {verify_dir})

        res = exec_runner.run_prompt(
            prompt="\n".join(prompt_parts),
            working_directory=str(work_dir),
            timeout_seconds=cfg.default_timeout_seconds,
            additional_dirs=extra_dirs or None,
            target_file=str(dest_path),
            conversation_id=conversation_id or None,
            model=model,
            effort=effort,
        )

        verification: Optional[Verification] = None
        if verify_command:
            verification = exec_verifier.run(
                command=verify_command,
                working_directory=verify_dir,
                timeout_seconds=cfg.verify_timeout_seconds,
            )

        log_delegation(
            cfg.log_path,
            "delegate_code_draft",
            res,
            verified=verification.passed if verification else None,
        )

        review = (
            [
                "The check passes, so behavior is proven — read the diff for design, not for bugs.",
                "Confirm the check actually covers the specification's edge cases.",
                "Check the standards: Pydantic models, Protocols for DI, BaseSettings, no"
                " os.environ, no lazy imports.",
            ]
            if verification and verification.passed
            else [
                f"Read {dest_path} in full — nothing proves this works.",
                "Check the standards: Pydantic models, Protocols for DI, BaseSettings, no"
                " os.environ, no lazy imports.",
                "Run the tests yourself.",
            ]
        )
        return _format_response(
            "Code Draft Delegation",
            res,
            review,
            target_file=str(dest_path),
            notes=notes,
            verification=verification,
        )

    @server.tool()
    def delegate_vault_document(
        relative_path: Annotated[
            str,
            Field(
                description=(
                    "Path inside ~/.vault/, e.g. 'wiki/repos/gateway-service.md' or "
                    "'investigations/prod-incident.md'."
                )
            ),
        ],
        topic: Annotated[str, Field(description="Subject of the document.")],
        source_context: Annotated[
            str,
            Field(
                description=(
                    "The factual basis: findings, decisions, config values, file paths. agy can "
                    "read files itself, so reference paths rather than pasting long excerpts."
                )
            ),
        ],
        template_name: Annotated[
            str,
            Field(
                description=(
                    "Template stem in ~/.vault/_templates/ (wiki, investigation, project, "
                    "plan-index, review, meeting-one-on-one). Inferred from relative_path if omitted."
                )
            ),
        ] = "",
        model: Annotated[Optional[str], MODEL_FIELD] = None,
        effort: Annotated[Optional[Effort], EFFORT_FIELD] = None,
    ) -> str:
        """Delegate drafting a vault page to agy, following the vault schema and templates.

        Prose has no verifier, so you carry the whole review. Best for long pages built from
        facts you supply. For anything where correctness matters more than volume, consider
        delegate_task with an output_schema to gather the facts and write the page yourself.
        Never use it for one-line edits such as a wiki/log.md entry.
        """
        clean_rel_path = relative_path.lstrip("/")
        target_file = cfg.vault_path / clean_rel_path

        created_dir: Optional[Path] = None
        if not target_file.parent.exists():
            target_file.parent.mkdir(parents=True, exist_ok=True)
            created_dir = target_file.parent

        notes: List[str] = []
        resolved_template = template_name
        if not resolved_template:
            for folder, stem in TEMPLATE_BY_FOLDER.items():
                if clean_rel_path.startswith(folder):
                    resolved_template = stem
                    break

        template_content = ""
        if resolved_template:
            tmpl_file = cfg.vault_templates_path / f"{resolved_template.removesuffix('.md')}.md"
            if tmpl_file.exists():
                template_content = tmpl_file.read_text(encoding="utf-8")
                notes.append(f"Template: {tmpl_file.name}")
            else:
                notes.append(
                    f"Template '{resolved_template}' not found in {cfg.vault_templates_path}"
                )

        prompt_parts = [
            f"Write a vault document about: {topic}",
            f"Write the finished content into this file: {target_file}",
            "",
            prompts.WRITING_STYLE,
            "",
            f"- {prompts.OBSIDIAN_LINKS}",
            f"- {prompts.NO_CUSTOMER_NAMES}",
        ]

        schema_file = cfg.vault_schema_path
        if schema_file.exists():
            prompt_parts.extend(
                [
                    "",
                    "The vault schema below is authoritative for folder layout, page structure,"
                    " and conventions. Follow it.",
                    "--- vault schema.md ---",
                    schema_file.read_text(encoding="utf-8"),
                    "--- end vault schema.md ---",
                ]
            )
            notes.append("Vault schema included")

        if template_content:
            prompt_parts.extend(
                [
                    "",
                    "Required template structure:",
                    "--- template ---",
                    template_content,
                    "--- end template ---",
                ]
            )

        prompt_parts.extend(
            [
                "",
                "Source context and details:",
                source_context,
                "",
                f"Write the file now: {target_file}",
            ]
        )

        res = exec_runner.run_prompt(
            prompt="\n".join(prompt_parts),
            working_directory=str(cfg.vault_path),
            timeout_seconds=cfg.default_timeout_seconds,
            target_file=str(target_file),
            model=model,
            effort=effort,
        )

        if not target_file.exists() and created_dir is not None:
            try:
                if not any(created_dir.iterdir()):
                    created_dir.rmdir()
            except OSError:
                pass

        # agy will claim it wrote a file it did not write, so check the disk.
        wrote_file = target_file.exists()
        if not wrote_file:
            notes.append("agy did not create the file, whatever its summary says")
        log_delegation(cfg.log_path, "delegate_vault_document", res, verified=wrote_file)

        return _format_response(
            "Vault Document Delegation",
            res,
            [
                f"Read {target_file} and check it against ~/.vault/schema.md and the template.",
                "Verify every factual claim — prose has no verifier and agy invents plausible"
                " details such as line counts.",
                "Interrogate the prose: plain English, concrete, no sentence that does not earn"
                " its place.",
                "Confirm no real customer or tenant names appear.",
                "Add a wiki/log.md entry yourself: YYYY-MM-DD | ACTION | page-name | description.",
                "Update ~/.vault/INDEX.md yourself if this adds a top-level page.",
            ],
            target_file=str(target_file),
            notes=notes,
        )

    @server.tool()
    def refine_delegation(
        conversation_id: Annotated[
            str,
            Field(description="Conversation id from an earlier delegation's response."),
        ],
        feedback: Annotated[
            str,
            Field(
                description=(
                    "The specific corrections to apply. Be concrete: what is wrong, where, and "
                    "what it should be instead."
                )
            ),
        ],
        working_directory: Annotated[
            str, Field(description="Absolute path agy runs in. Must match the original call.")
        ] = "",
        target_file: Annotated[
            str, Field(description="File under revision, for the review reminder.")
        ] = "",
        verify_command: Annotated[
            str,
            Field(
                description=(
                    "Command proving the correction worked. This server re-runs it after agy "
                    "finishes. Pass the same one used for the original draft."
                )
            ),
        ] = "",
        verify_directory: Annotated[
            str, Field(description="Directory to run verify_command from.")
        ] = "",
        timeout_seconds: Annotated[int, Field(description="Wall-clock budget.", ge=30)] = 300,
        model: Annotated[Optional[str], MODEL_FIELD] = None,
        effort: Annotated[Optional[Effort], EFFORT_FIELD] = None,
    ) -> str:
        """Send corrections back to an earlier agy delegation instead of rewriting its output.

        agy still holds the original context, so it re-reads almost nothing. Prefer this over
        fixing a long draft yourself; then re-read only to verify.
        """
        work_dir = working_directory or str(cfg.dev_path)
        feedback_block = f"Apply these corrections to your previous work:\n\n{feedback}"
        if verify_command:
            verify_dir = verify_directory or work_dir
            feedback_block += "\n\n" + prompts.verify_loop(
                verify_command, verify_dir, cfg.max_verify_rounds
            )
        else:
            feedback_block += "\n\nThen confirm what changed."

        res = exec_runner.run_prompt(
            prompt=feedback_block,
            working_directory=work_dir,
            timeout_seconds=timeout_seconds,
            target_file=target_file or None,
            conversation_id=conversation_id,
            model=model,
            effort=effort,
        )

        verification: Optional[Verification] = None
        if verify_command:
            verification = exec_verifier.run(
                command=verify_command,
                working_directory=verify_directory or work_dir,
                timeout_seconds=cfg.verify_timeout_seconds,
            )

        log_delegation(
            cfg.log_path,
            "refine_delegation",
            res,
            verified=verification.passed if verification else None,
            refine_of=conversation_id,
        )

        return _format_response(
            "Refinement",
            res,
            [
                "Re-read only the parts you asked it to change.",
                "Confirm the correction landed and nothing else regressed.",
            ],
            target_file=target_file or None,
            verification=verification,
        )

    @server.tool()
    def delegation_stats(
        limit: Annotated[
            int,
            Field(description="How many of the most recent delegations to summarize.", ge=1),
        ] = 50,
    ) -> str:
        """Report whether delegating is actually paying off, from the recorded delegation log.

        Read this before assuming the setup saves anything. Without measurement a delegation
        that failed twice and needed three corrections looks the same as one that worked.
        """
        if not cfg.log_path.exists():
            return f"No delegation log yet at {cfg.log_path}."

        rows: List[Dict[str, Any]] = []
        for line in cfg.log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        if not rows:
            return f"Delegation log at {cfg.log_path} has no readable entries."

        recent = rows[-limit:]
        total = len(recent)
        refines = sum(1 for r in recent if r.get("refine_of"))
        first_attempts = total - refines
        agy_ok = sum(1 for r in recent if r.get("agy_reported_success"))
        checked = [r for r in recent if r.get("verified") is not None]
        verified_ok = sum(1 for r in checked if r.get("verified"))
        disagreed = sum(
            1
            for r in checked
            if bool(r.get("verified")) != bool(r.get("agy_reported_success"))
        )
        tokens_in = sum(r.get("input_tokens") or 0 for r in recent)
        tokens_out = sum(r.get("output_tokens") or 0 for r in recent)
        cached = sum(r.get("cached_tokens") or 0 for r in recent)
        seconds = sum(r.get("duration_s") or 0 for r in recent)

        by_tool: Dict[str, int] = {}
        for r in recent:
            by_tool[str(r.get("tool"))] = by_tool.get(str(r.get("tool")), 0) + 1

        lines = [
            f"=== Delegation stats (last {total} of {len(rows)}) ===",
            f"Log: {cfg.log_path}",
            "",
            f"First attempts: {first_attempts} · corrections sent back: {refines}",
        ]
        if first_attempts:
            lines.append(
                f"Correction rate: {refines / first_attempts:.0%} of first attempts needed a refine"
            )
        lines.append(f"agy reported success: {agy_ok}/{total}")
        if checked:
            lines.append(f"Independently verified: {verified_ok}/{len(checked)} passed")
            lines.append(
                f"agy's status disagreed with the check {disagreed} time(s)"
                " — a reminder not to trust its self-report"
            )
        else:
            lines.append(
                "Nothing was independently verified. Pass verify_command so a pass is observed."
            )
        lines.extend(
            [
                "",
                f"agy tokens: {tokens_in:,} in / {tokens_out:,} out ({cached:,} cached)",
                f"agy wall-clock: {seconds / 60:.0f} min",
                "",
                "By tool: " + ", ".join(f"{k}={v}" for k, v in sorted(by_tool.items())),
                "",
                "Compare against what these drafts would have cost you to write directly."
                " A delegation that needed several corrections was probably a loss.",
            ]
        )
        return "\n".join(lines)

    return server
