from pathlib import Path
from typing import Annotated, List, Optional
from mcp.server.mcpserver import MCPServer
from pydantic import Field
from antigravity_mcp import prompts
from antigravity_mcp.config import Settings
from antigravity_mcp.models import ExecutionResult
from antigravity_mcp.protocols import AgyRunnerProtocol
from antigravity_mcp.runner import AgyRunner

TEMPLATE_BY_FOLDER = {
    "wiki/": "wiki",
    "investigations/": "investigation",
    "projects/": "project",
    "plans/": "plan-index",
    "meetings/": "meeting-one-on-one",
}


def _status_header(title: str, res: ExecutionResult) -> str:
    state = "SUCCESS" if res.success else f"FAILED (exit code {res.exit_code})"
    return f"=== {title}: {state} ==="


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
) -> str:
    lines = [_status_header(title, res)]
    if target_file:
        lines.append(f"Target file: {target_file}")
    usage = _usage_line(res)
    if usage:
        lines.append(usage)
    for note in notes or []:
        lines.append(f"Note: {note}")
    lines.append("")

    if not res.success:
        lines.extend(["--- Error ---", res.stderr or "(no error output)"])
        if res.stdout:
            lines.extend(["", "--- Partial output ---", res.stdout])
        lines.extend(
            [
                "",
                "Nothing was produced to review. Diagnose the failure or do the work directly;",
                "do not retry the same delegation blind.",
            ]
        )
        return "\n".join(lines)

    lines.extend(["--- Output ---", res.stdout or "(written to file, no summary returned)"])
    if res.stderr:
        lines.extend(["", "--- Warnings ---", res.stderr])

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
) -> MCPServer:
    cfg = settings or Settings()
    exec_runner = runner or AgyRunner(cfg)

    server = MCPServer("antigravity-worker")

    @server.tool()
    def delegate_task(
        instruction: Annotated[
            str,
            Field(
                description=(
                    "Self-contained instruction for agy. It has file read/write tools and runs "
                    "in working_directory, so name the paths it should read instead of pasting "
                    "their contents."
                )
            ),
        ],
        working_directory: Annotated[
            str,
            Field(description="Absolute path agy runs in. Defaults to ~/dev (all repos)."),
        ] = "",
        timeout_seconds: Annotated[
            int,
            Field(description="Wall-clock budget for agy. Raise it for multi-file work.", ge=30),
        ] = 300,
        additional_dirs: Annotated[
            Optional[List[str]],
            Field(description="Extra absolute paths to add to agy's workspace."),
        ] = None,
    ) -> str:
        """Delegate bulk reading or drafting to agy (Gemini 3.7 Flash, high effort).

        Use for summarizing large logs, sweeping several repos, or drafting long prose.
        Do not use for work smaller than the review it triggers: reviewing the result costs a
        full read, so short edits are cheaper done directly.
        """
        work_dir = working_directory or str(cfg.dev_path)
        res = exec_runner.run_prompt(
            prompt=instruction,
            working_directory=work_dir,
            timeout_seconds=timeout_seconds,
            additional_dirs=additional_dirs,
        )
        return _format_response(
            "Antigravity Execution",
            res,
            [
                "Check the output for accuracy, consistency, and gaps.",
                "Inspect any file it created or changed with Read or Grep.",
                "If it wrote code, run pytest and check typing and linting.",
            ],
            notes=[f"Working directory: {work_dir}"],
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
    ) -> str:
        """Delegate drafting a vault page to agy, following the vault schema and templates.

        For new pages and substantial rewrites. Do not use for one-line edits such as a
        wiki/log.md entry or an INDEX.md pointer — write those directly.
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
                notes.append(f"Template '{resolved_template}' not found in {cfg.vault_templates_path}")

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
                ["", "Required template structure:", "--- template ---", template_content, "--- end template ---"]
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
        )

        if not res.success and created_dir is not None:
            try:
                if not any(created_dir.iterdir()):
                    created_dir.rmdir()
            except OSError:
                pass

        return _format_response(
            "Vault Document Delegation",
            res,
            [
                f"Read {target_file} and check it against ~/.vault/schema.md and the template.",
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
    def delegate_code_draft(
        target_file: Annotated[
            str, Field(description="Absolute path of the file agy should write.")
        ],
        task_description: Annotated[
            str,
            Field(description="What the code must do, including edge cases and expected behavior."),
        ],
        context_files: Annotated[
            Optional[List[str]],
            Field(
                description=(
                    "Absolute paths agy should read for context. Paths only — agy reads them "
                    "itself; do not paste file contents into task_description."
                )
            ),
        ] = None,
    ) -> str:
        """Delegate drafting code, boilerplate, or a test suite to agy.

        Best for whole files and test suites, roughly 150 lines or more. Below that, the
        mandatory review costs more than writing it directly.
        """
        dest_path = Path(target_file)
        paths = [Path(p) for p in context_files or []]
        missing = [str(p) for p in paths if not p.exists()]
        present = [p for p in paths if p.exists()]

        notes: List[str] = []
        if missing:
            notes.append(f"Context files not found and skipped: {', '.join(missing)}")

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

        prompt_parts.extend(["", f"Write the implementation into {dest_path} now."])

        work_dir = dest_path.parent if dest_path.parent.exists() else cfg.dev_path
        extra_dirs = sorted(
            {str(p.parent) for p in present if str(p.parent) != str(work_dir)}
        )

        res = exec_runner.run_prompt(
            prompt="\n".join(prompt_parts),
            working_directory=str(work_dir),
            timeout_seconds=cfg.default_timeout_seconds,
            additional_dirs=extra_dirs or None,
            target_file=str(dest_path),
        )
        return _format_response(
            "Code Draft Delegation",
            res,
            [
                f"Read {dest_path} in full.",
                "Check the standards: Pydantic models, Protocols for DI, BaseSettings, no"
                " os.environ, no lazy imports.",
                "Run pytest.",
                "Check the edge cases named in the specification are actually handled.",
            ],
            target_file=str(dest_path),
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
        timeout_seconds: Annotated[int, Field(description="Wall-clock budget.", ge=30)] = 300,
    ) -> str:
        """Send corrections back to an earlier agy delegation instead of rewriting its output.

        agy still holds the original context, so it re-reads almost nothing. Prefer this over
        fixing a long draft yourself; then re-read only to verify.
        """
        res = exec_runner.run_prompt(
            prompt=(
                f"Apply these corrections to your previous work, then confirm what changed:\n\n{feedback}"
            ),
            working_directory=working_directory or str(cfg.dev_path),
            timeout_seconds=timeout_seconds,
            target_file=target_file or None,
            conversation_id=conversation_id,
        )
        return _format_response(
            "Refinement",
            res,
            [
                "Re-read only the parts you asked it to change.",
                "Confirm the correction landed and nothing else regressed.",
                "Re-run pytest if this was code.",
            ],
            target_file=target_file or None,
        )

    return server
