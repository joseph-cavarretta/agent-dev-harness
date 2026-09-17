# Vault Preferences

Optional module for machines with a `~/.vault/` knowledge base. Imported from `~/.claude/CLAUDE.md`
with `@CLAUDE.vault.md`, after `@CLAUDE.base.md`.

## Knowledge Base (Vault)

A vault-backed knowledge base is the standard way of working: read it at the start of a
session for grounding, update it after substantive work. If a machine has no `~/.vault/`,
these instructions simply no-op.

### Structure
- **Vault location:** `~/.vault/`
- **Templates:** `~/.vault/_templates/` — MUST read and use the matching template when creating new vault notes
- **Folders:** `wiki/` (technical reference: systems, repos, runbooks, decisions, patterns), `notes/` (working notes), `projects/` (multi-file initiatives), `plans/` (index notes pointing to full plans), `investigations/` (incident & debugging writeups), `archive/`

### Plans — two parts
1. `~/.vault/plans/<slug>.md` — short vault index note: title, date, link to plan file, project, 2–3 sentence summary. Use `_templates/plan-index.md`.
2. `~/.claude/plans/<slug>.md` — the full implementation plan: scope, approach, key files, risks.

### Before working
1. Read `~/.vault/INDEX.md` — top-level entry point for the whole vault
2. Pre-load the Core Reference pages listed there for grounding
3. Open only the specific wiki pages the task touches; skip patterns/runbooks unless the task is operational
- Fast path: single-repo task → skip INDEX.md, go straight to `wiki/repos/<repo>.md`
- Operational incident → check `investigations/` before diagnosing

### After substantive work
1. Update or create wiki pages for findings — new pages and substantial rewrites go through `delegate_vault_document`; write the `INDEX.md` and `log.md` lines yourself
2. Update `~/.vault/INDEX.md` to reflect new/changed pages
3. Append to `wiki/log.md` (`YYYY-MM-DD | ACTION | page | description`)
4. Lint on demand using the checklist in `~/.vault/schema.md`

### Conventions
- Filenames: lowercase, hyphens (`my-service.md`)
- Links: Obsidian `[[wiki/folder/page-name]]` syntax
- Never include real customer or tenant names — use `<tenant>`, `<slug>`, `<env>`
- Prefer updating existing pages over creating new ones
- Staleness marker: add `*(stale, YYYY-MM-DD)*` if a page is 60+ days old
- Convert relative dates to absolute when writing notes

### Delegating vault documents
- `delegate_vault_document` for long prose built from facts supplied. No verifier, so the whole review lands on Claude.
- Don't delegate one-line `INDEX.md` or `wiki/log.md` entries — write them yourself.
