from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from delegate_mcp.app import code_draft, refine, stats, task, vault_document
from delegate_mcp.app.context import AppContext
from delegate_mcp.models import (
    CodeDraftRequest,
    Effort,
    JsonObject,
    RefineRequest,
    TaskRequest,
    VaultDocumentRequest,
)

# Tool and parameter descriptions are the calling agent's only documentation, so
# every one is spelled out. Defaults live in the request models in models.py.
Model = Annotated[
    str | None,
    Field(
        description=(
            "Worker model id. Omit for the configured default. Use a stronger model "
            "only for genuinely hard reasoning; an unknown id is a hard error listing "
            "valid ones."
        )
    ),
]
EffortParam = Annotated[
    Effort | None,
    Field(
        description=(
            "Reasoning effort. Use 'low' for mechanical work, 'high' only when the "
            "task needs it. Omit for the configured default."
        )
    ),
]
Timeout = Annotated[
    int,
    Field(
        description="Wall-clock budget for the worker. Raise it for multi-file work.",
        ge=30,
    ),
]


DELEGATE_TASK_DESCRIPTION = (
    "Delegate bulk reading, searching, or summarizing to the worker.\n\n"
    "This is the tool with the best economics: the worker reads a lot and returns a "
    "little. Pass output_schema whenever you will act on the result "
    "programmatically. Do not use it for work smaller than the review it triggers."
)

DELEGATE_CODE_DRAFT_DESCRIPTION = (
    "Delegate drafting code or tests to the worker, ideally against a command that proves it works.\n\n"
    "With verify_command the economics change: the worker loops until the check "
    "passes and you review a green artifact instead of auditing prose. Without one, "
    "only delegate whole files — the review costs more than writing short code "
    "yourself."
)

DELEGATE_VAULT_DOCUMENT_DESCRIPTION = (
    "Delegate drafting a vault page to the worker, following the vault schema and templates.\n\n"
    "Prose has no verifier, so you carry the whole review. Best for long pages "
    "built from facts you supply. For anything where correctness matters more than "
    "volume, consider delegate_task with an output_schema to gather the facts and "
    "write the page yourself. Never use it for one-line edits such as a wiki/log.md "
    "entry."
)

REFINE_DELEGATION_DESCRIPTION = (
    "Send corrections back to an earlier delegation instead of rewriting its output.\n\n"
    "The worker still holds the original context, so it re-reads almost nothing. "
    "Prefer this over fixing a long draft yourself; then re-read only to verify."
)

DELEGATION_STATS_DESCRIPTION = (
    "Report whether delegating is actually paying off, from the recorded delegation log.\n\n"
    "Read this before assuming the setup saves anything. Without measurement a "
    "delegation that failed twice and needed three corrections looks the same as "
    "one that worked."
)


def _register_task(server: MCPServer, ctx: AppContext) -> None:
    """Add delegate_task."""

    @server.tool(description=DELEGATE_TASK_DESCRIPTION)
    def delegate_task(  # noqa: PLR0913, PLR0917  # MCP exposes each argument
        instruction: Annotated[
            str,
            Field(
                description=(
                    "Self-contained instruction for the worker. It has file read/write "
                    "and terminal tools and runs in working_directory, so name the "
                    "paths it should read instead of pasting their contents."
                )
            ),
        ],
        working_directory: Annotated[
            str,
            Field(
                description=(
                    "Absolute path the worker runs in. Defaults to ~/dev (all repos)."
                )
            ),
        ] = "",
        output_schema: Annotated[
            JsonObject | None,
            Field(
                description=(
                    "JSON Schema for the answer. Supply this whenever you will consume "
                    "the result rather than read prose: the worker is forced to "
                    "conform and the validated object comes back separately from its "
                    "chatter. Strongly preferred for findings, extractions, and "
                    "summaries."
                )
            ),
        ] = None,
        timeout_seconds: Timeout = 300,
        additional_dirs: Annotated[
            list[str] | None,
            Field(description="Extra absolute paths to add to the worker's workspace."),
        ] = None,
        conversation_id: Annotated[
            str,
            Field(
                description=(
                    "Continue an earlier delegation's conversation. Reuses its cached "
                    "context, so batching related work into one conversation is much "
                    "cheaper than separate cold calls."
                )
            ),
        ] = "",
        model: Model = None,
        effort: EffortParam = None,
    ) -> str:
        """Handle a delegate_task call."""
        return task.delegate_task(
            ctx,
            TaskRequest(
                instruction=instruction,
                working_directory=working_directory,
                output_schema=output_schema,
                timeout_seconds=timeout_seconds,
                additional_dirs=additional_dirs,
                conversation_id=conversation_id,
                model=model,
                effort=effort,
            ),
        )


def _register_code_draft(server: MCPServer, ctx: AppContext) -> None:
    """Add delegate_code_draft."""

    @server.tool(description=DELEGATE_CODE_DRAFT_DESCRIPTION)
    def delegate_code_draft(  # noqa: PLR0913, PLR0917  # MCP exposes each argument
        target_file: Annotated[
            str, Field(description="Absolute path of the file the worker should write.")
        ],
        task_description: Annotated[
            str,
            Field(
                description=(
                    "What the code must do, including edge cases and expected behavior."
                )
            ),
        ],
        verify_command: Annotated[
            str,
            Field(
                description=(
                    "Shell command that proves the work is correct, e.g. 'uv run pytest "
                    "tests/test_worker.py -q'. The worker iterates against it until it "
                    "passes, then this server re-runs it independently. Supply it "
                    "whenever one exists — it is what makes delegating cheaper than "
                    "writing the code yourself."
                )
            ),
        ] = "",
        verify_directory: Annotated[
            str,
            Field(
                description=(
                    "Directory to run verify_command from, usually the repo root. "
                    "Defaults to the target file's parent."
                )
            ),
        ] = "",
        context_files: Annotated[
            list[str] | None,
            Field(
                description=(
                    "Absolute paths the worker should read for context. Paths only — "
                    "it reads them itself; do not paste file contents into "
                    "task_description."
                )
            ),
        ] = None,
        conversation_id: Annotated[
            str,
            Field(
                description=(
                    "Continue an earlier conversation, for drafting several related "
                    "files with its context already warm."
                )
            ),
        ] = "",
        model: Model = None,
        effort: EffortParam = None,
    ) -> str:
        """Handle a delegate_code_draft call."""
        return code_draft.delegate_code_draft(
            ctx,
            CodeDraftRequest(
                target_file=target_file,
                task_description=task_description,
                verify_command=verify_command,
                verify_directory=verify_directory,
                context_files=context_files,
                conversation_id=conversation_id,
                model=model,
                effort=effort,
            ),
        )


def _register_vault_document(server: MCPServer, ctx: AppContext) -> None:
    """Add delegate_vault_document."""

    @server.tool(description=DELEGATE_VAULT_DOCUMENT_DESCRIPTION)
    def delegate_vault_document(  # MCP exposes each argument
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
                    "The factual basis: findings, decisions, config values, file "
                    "paths. The worker can read files itself, so reference paths "
                    "rather than pasting long excerpts."
                )
            ),
        ],
        template_name: Annotated[
            str,
            Field(
                description=(
                    "Template stem in ~/.vault/_templates/ (wiki, investigation, "
                    "project, plan-index, review, meeting-one-on-one). Inferred from "
                    "relative_path if omitted."
                )
            ),
        ] = "",
        model: Model = None,
        effort: EffortParam = None,
    ) -> str:
        """Handle a delegate_vault_document call."""
        return vault_document.delegate_vault_document(
            ctx,
            VaultDocumentRequest(
                relative_path=relative_path,
                topic=topic,
                source_context=source_context,
                template_name=template_name,
                model=model,
                effort=effort,
            ),
        )


def _register_refine(server: MCPServer, ctx: AppContext) -> None:
    """Add refine_delegation."""

    @server.tool(description=REFINE_DELEGATION_DESCRIPTION)
    def refine_delegation(  # noqa: PLR0913, PLR0917  # MCP exposes each argument
        conversation_id: Annotated[
            str,
            Field(description="Conversation id from an earlier delegation's response."),
        ],
        feedback: Annotated[
            str,
            Field(
                description=(
                    "The specific corrections to apply. Be concrete: what is wrong, "
                    "where, and what it should be instead."
                )
            ),
        ],
        working_directory: Annotated[
            str,
            Field(
                description=(
                    "Absolute path the worker runs in. Must match the original call."
                )
            ),
        ] = "",
        target_file: Annotated[
            str, Field(description="File under revision, for the review reminder.")
        ] = "",
        verify_command: Annotated[
            str,
            Field(
                description=(
                    "Command proving the correction worked. This server re-runs it "
                    "after the worker finishes. Pass the same one used for the "
                    "original draft."
                )
            ),
        ] = "",
        verify_directory: Annotated[
            str, Field(description="Directory to run verify_command from.")
        ] = "",
        timeout_seconds: Annotated[
            int, Field(description="Wall-clock budget.", ge=30)
        ] = 300,
        model: Model = None,
        effort: EffortParam = None,
    ) -> str:
        """Handle a refine_delegation call."""
        return refine.refine_delegation(
            ctx,
            RefineRequest(
                conversation_id=conversation_id,
                feedback=feedback,
                working_directory=working_directory,
                target_file=target_file,
                verify_command=verify_command,
                verify_directory=verify_directory,
                timeout_seconds=timeout_seconds,
                model=model,
                effort=effort,
            ),
        )


def _register_stats(server: MCPServer, ctx: AppContext) -> None:
    """Add delegation_stats."""

    @server.tool(description=DELEGATION_STATS_DESCRIPTION)
    def delegation_stats(
        limit: Annotated[
            int,
            Field(
                description="How many of the most recent delegations to summarize.",
                ge=1,
            ),
        ] = 50,
    ) -> str:
        """Handle a delegation_stats call."""
        return stats.delegation_stats(ctx, limit)


def create_server(ctx: AppContext) -> MCPServer:
    """The delegate MCP server with every tool registered against ctx."""
    server = MCPServer("delegate")
    _register_task(server, ctx)
    _register_code_draft(server, ctx)
    # Only offered where a vault exists, so the server also works on machines without
    # one.
    if ctx.settings.vault_path.exists():
        _register_vault_document(server, ctx)
    _register_refine(server, ctx)
    _register_stats(server, ctx)
    return server
