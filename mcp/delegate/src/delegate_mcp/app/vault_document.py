import logging
from pathlib import Path

from delegate_mcp.app.context import AppContext
from delegate_mcp.core import prompts
from delegate_mcp.core.formatting import format_response
from delegate_mcp.core.vault import template_stem
from delegate_mcp.infra.delegation_log import log_delegation
from delegate_mcp.models import ResponseReport, VaultDocumentRequest, WorkerRun

logger = logging.getLogger(__name__)

_REVIEW = [
    "Verify every factual claim — prose has no verifier and the worker invents"
    " plausible details such as line counts.",
    "Interrogate the prose: plain English, concrete, no sentence that does not earn"
    " its place.",
    "Confirm no real customer or tenant names appear.",
    "Add a wiki/log.md entry yourself: YYYY-MM-DD | ACTION | page-name | description.",
    "Update ~/.vault/INDEX.md yourself if this adds a top-level page.",
]


def _template_text(ctx: AppContext, stem: str, notes: list[str]) -> str:
    """The named template's text, noting in `notes` whether it was found."""
    if not stem:
        return ""
    templates = ctx.settings.vault_templates_path
    tmpl_file = templates / f"{stem.removesuffix('.md')}.md"
    if not tmpl_file.exists():
        notes.append(f"Template '{stem}' not found in {templates}")
        return ""
    notes.append(f"Template: {tmpl_file.name}")
    return tmpl_file.read_text(encoding="utf-8")


def _remove_if_empty(directory: Path) -> None:
    """Remove a directory this call created, if the worker left it empty."""
    try:
        if not any(directory.iterdir()):
            directory.rmdir()
    except OSError:
        logger.warning("could not clean up %s", directory, exc_info=True)


def delegate_vault_document(ctx: AppContext, request: VaultDocumentRequest) -> str:
    """Have the worker write one vault page, then check on disk that it exists."""
    clean_rel_path = request.relative_path.lstrip("/")
    target_file = ctx.settings.vault_path / clean_rel_path
    created_dir: Path | None = None
    if not target_file.parent.exists():
        target_file.parent.mkdir(parents=True, exist_ok=True)
        created_dir = target_file.parent

    notes: list[str] = []
    template_text = _template_text(
        ctx, template_stem(clean_rel_path, request.template_name), notes
    )
    schema_file = ctx.settings.vault_schema_path
    schema_text = None
    if schema_file.exists():
        schema_text = schema_file.read_text(encoding="utf-8")
        notes.append("Vault schema included")

    res = ctx.runner.run(
        WorkerRun(
            prompt=prompts.vault_document_prompt(
                request.topic,
                target_file,
                request.source_context,
                schema_text,
                template_text,
            ),
            working_directory=str(ctx.settings.vault_path),
            timeout_seconds=ctx.settings.default_timeout_seconds,
            target_file=str(target_file),
            model=request.model,
            effort=request.effort,
        )
    )

    # The worker will claim it wrote a file it did not write, so check the disk.
    wrote_file = target_file.exists()
    if not wrote_file:
        if created_dir is not None:
            _remove_if_empty(created_dir)
        notes.append("The worker did not create the file, whatever its summary says")
    log_delegation(
        ctx.settings.log_path, "delegate_vault_document", res, verified=wrote_file
    )
    return format_response(
        ResponseReport(
            title="Vault Document Delegation",
            result=res,
            review_steps=[
                f"Read {target_file} and check it against ~/.vault/schema.md and the "
                "template.",
                *_REVIEW,
            ],
            target_file=str(target_file),
            notes=notes,
        )
    )
