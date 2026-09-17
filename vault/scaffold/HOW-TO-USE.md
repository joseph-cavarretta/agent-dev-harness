# Vault Bootstrap Template

A shareable skeleton for managing a knowledge base with Claude Code. Claude maintains the
vault as a byproduct of real work — it grows richer over time without extra effort.

This directory is **content only**. The Claude Code configuration that drives it (session
conventions, hooks, permissions) lives in the harness `vault/` module, not here — see
[Configuration](#configuration) below.

## What's Included

| File/Dir | Purpose |
|---|---|
| `schema.md` | Vault-wide conventions: folders, templates, naming, lint checklist |
| `INDEX.md` | Top-level vault index (customize with your content) |
| `wiki/` | Technical knowledge base (log, subdirs) |
| `_templates/` | Boilerplate for investigations, plans, projects, reviews |
| `plans/`, `notes/`, `projects/`, `investigations/` | Empty directories ready for content |

## Quick Start

1. Copy this scaffold to `~/.vault` on the workstation (`make vault-init` from the harness
   repo, or `cp -r vault/scaffold/ ~/.vault`). It will not overwrite an existing vault.
2. Customize `INDEX.md` with your actual systems, repos, and pages
3. List your 2–4 most-used pages under **Core Reference** in `INDEX.md`, and point
   `vault/hooks/preload-core-reference.py` at them
4. Add your first wiki pages under `wiki/systems/` and `wiki/repos/`

## Core Idea

The vault serves as persistent memory. Claude reads it at the start of each session and
updates it after substantive work. Over time it accumulates architecture docs, decision
rationale, runbooks, and patterns that would otherwise live only in commit messages or
people's heads.

The two-way flow:
- **Into Claude:** pre-load `INDEX.md` + Core Reference pages every session to ground responses
- **Out of Claude:** after meaningful work, update or create wiki pages and append to `wiki/log.md`

## Structure

### `wiki/` — Technical Knowledge Base

| Subfolder | What goes here |
|---|---|
| `systems/` | Architecture, data flow, and component maps for major services |
| `repos/` | Per-repo guides: structure, commands, conventions, gotchas |
| `runbooks/` | Operational procedures and troubleshooting steps |
| `decisions/` | Design decisions and their trade-offs |
| `patterns/` | Coding patterns, workflows, and shared conventions |

Each wiki page has a `**Last updated:**` date and `**Sources:**` field so you know how fresh it is.

### `plans/` — Implementation Plan Index

Short index notes pointing to full plans in `~/.claude/plans/`. Each entry has title, date,
project, the plan file path, and a 2–3 sentence summary. Use `_templates/plan-index.md`.

### `projects/` — Multi-file Initiatives

Folders for ongoing work with multiple related files — diagrams, design reviews, cost
analyses, etc. Use `_templates/project.md`.

### `notes/` — Working Notes

Findings, procedure reminders, roadmap sketches. Timestamped filenames: `topic-YYYY-MM-DD.md`.
No rigid template — `# Title`, `**Date:**`, `**Project:**`, then `##` sections.

### `investigations/` — Incidents & Debugging

Root-cause analyses of incidents. Self-contained with timeline, evidence, and fix. Use
`_templates/investigation.md`.

### `_templates/` — Boilerplate

| Template | Use for |
|---|---|
| `investigation.md` | Incident and debugging writeups |
| `plan-index.md` | Vault index note for a new plan |
| `project.md` | A new multi-file initiative |
| `review.md` | Design or technical reviews |

## Navigation

`INDEX.md` is the single entry point for the whole vault. It lists Core Reference pages — the
2–4 pages needed in almost every session — which the `preload-core-reference.py` hook injects
into every session automatically.

Fast paths:
- **Single-repo task:** skip INDEX.md, go straight to `wiki/repos/<repo>.md`
- **Operational incident:** check `investigations/` before diagnosing

## Conventions

- **Filenames:** lowercase, hyphens, no spaces (`my-service.md`)
- **Links:** Obsidian `[[wiki/folder/page-name]]` syntax
- **Staleness:** pages not updated in 60+ days get `*(stale, YYYY-MM-DD)*` in INDEX.md
- **Customers/tenants:** never use real names — use `<tenant>`, `<slug>`, `<env>`
- **Page size:** if a page exceeds ~300 lines, split into sub-topics

Full conventions live in `schema.md`.

## Log

`wiki/log.md` is an append-only record of all vault changes, newest first:

```
- YYYY-MM-DD | CREATED | systems/my-system | Initial architecture doc
- YYYY-MM-DD | UPDATED | repos/my-repo | Added deployment targets
- YYYY-MM-DD | LINT | wiki-wide | Fixed orphans, updated staleness markers
```

When it exceeds ~150 lines, move entries older than 3 months to `wiki/log-archive.md`.

## Configuration

The vault's Claude Code setup is **not bundled here** — it lives in the harness so it stays a
single source of truth across machines. `make install-vault` wires it up:

- **Conventions** — how Claude reads and maintains the vault (before/after-work flow,
  templates, linting, log discipline) live in `vault/CLAUDE.vault.md`, imported from
  `~/.claude/CLAUDE.md` with `@CLAUDE.vault.md`.
- **Hooks** — `vault/hooks/` (vault) and `claude/hooks/` (general):
  | Hook | Event | Purpose |
  |---|---|---|
  | `preload-core-reference.py` | SessionStart | Injects Core Reference pages into every session |
  | `wiki-repo-staleness.py` | PostToolUse (Read) | Warns when a `wiki/repos` page is stale and the repo has new commits |
  | `audit-log.py` | PostToolUse (Bash) | Logs every shell command |
  | `secret-scanner.py` | PreToolUse (Write/Edit) | Blocks writes that look like secrets |
  | `git-commit-guard.py` | PreToolUse (Bash) | Guards `git commit` |
  | `precompact-snapshot.py` | PreCompact | Snapshots context before compaction |
- **Permissions & settings** — `claude/settings.json` (allow/deny baseline, hook wiring) and
  `vault/settings.json` (vault read access, vault hook wiring), merged into `~/.claude/settings.json`.

Point `preload-core-reference.py` at your own Core Reference pages after bootstrapping.
