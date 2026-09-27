# Vault Schema

## Purpose

This vault is Claude's persistent memory for infrastructure, systems, repos, and operational knowledge. Claude reads it at the start of sessions and updates it after substantive work. It captures knowledge that compounds — not ephemeral work items.

---

## Folder Structure

| Folder | What goes here | Template |
|---|---|---|
| `wiki/` | Technical knowledge base: systems, repos, runbooks, decisions, patterns | See §Wiki below |
| `plans/` | Short index notes pointing to full plans in `~/.claude/plans/` | `_templates/plan-index.md` |
| `projects/` | Multi-file initiatives: design docs, diagrams, reviews | `_templates/project.md` |
| `notes/` | Working notes: findings, procedures, roadmaps, meeting notes | (none — see §Notes) |
| `investigations/` | Incident and debugging writeups | `_templates/investigation.md` |
| `archive/` | Historical reference, superseded docs | (none) |
| `job-search/`, `interviews/` | Optional personal folders; see §Personal | `_templates/application.md`, `_templates/interview-guide.md` |

---

## Wiki

The wiki is a structured technical knowledge base maintained by Claude as a byproduct of working in repos.

### Subfolders

| Folder | What goes here | When to create a page |
|---|---|---|
| `systems/` | Architecture and data flow for a system or service | When Claude builds understanding of how a system works |
| `repos/` | Per-repo reference: structure, conventions, commands, key files, gotchas | First time Claude works meaningfully in a repo |
| `runbooks/` | Operational procedures, troubleshooting steps | When Claude helps debug or operate something |
| `decisions/` | Architectural decisions, trade-offs, "why we did X" | When Claude learns why a pattern or choice exists |
| `patterns/` | Coding guidelines, reusable patterns, conventions | When a pattern is established or documented |

### Page Template

```markdown
# <Title>

> <one-line summary; reused as the page's description in INDEX.md>

**Last updated:** YYYY-MM-DD
**Sources:** <repo paths, files, PRs, or conversations that informed this page>

---

<Content with ## headings. Be specific: include config values, file paths, command examples.
Link to related pages with [[wiki/folder/page-name]].>

## Open Questions (optional)

<Genuine unknowns. Remove when resolved. Omit the section entirely if there are none.>
```

### repos/ Pages

Repo pages replace per-repo CLAUDE.md files. Must include:
- Repo structure and key directories
- Test, lint, and build commands
- Coding conventions specific to this repo
- Deployment targets and environments
- Known gotchas and footguns

### Index and Log

- `wiki/log.md` — append-only change record, newest first
- `wiki/log-archive.md` — entries rotated out when log.md exceeds ~150 lines

**Log entry format:** `YYYY-MM-DD | ACTION | page-name | description`  
**Actions:** `CREATED`, `UPDATED`, `ENHANCE`, `RESTRUCTURE`, `LINT`

**Log compression:** when log.md exceeds ~150 lines, move entries older than 3 months to log-archive.md. Leave a note at the bottom: `*(entries before YYYY-MM-DD archived in [[wiki/log-archive]])*`

### Wiki Conventions

- Filenames: lowercase, hyphens, no spaces (`my-service.md`)
- Links: Obsidian `[[wiki/folder/page-name]]` syntax
- Never include real customer or tenant names — use `<tenant>`, `<slug>`, `<env>`
- Prefer updating an existing page over creating a new one
- If a page exceeds ~300 lines, split into sub-topics
- Staleness marker: add `*(stale, YYYY-MM-DD)*` in INDEX.md if not updated in 60+ days

---

## Plans

Plans split across two locations:

- **`~/.vault/plans/<slug>.md`** — Short vault index note. Use `_templates/plan-index.md`. Contains: title, date, plan file path, project, 2–3 sentence summary.
- **`~/.claude/plans/<slug>.md`** — Full implementation plan: scope, approach, key files, risks.

The vault note is the pointer; the implementation detail lives in `~/.claude/plans/`.

---

## Projects

Each project is a folder under `~/.vault/projects/` with an `index.md` entry point (use `_templates/project.md`) plus any supporting files (diagrams, notes, reviews).

---

## Notes

Working notes in `~/.vault/notes/`. No rigid template.

- **Filename:** `<topic>-<YYYY-MM-DD>.md` for time-specific notes; topic-only for evergreen reference notes
- **Header:** `# Title`, then `**Date:**`, `**Project:**` (if applicable), `**Purpose:**` (if not obvious from title), then `---`
- **Body:** `##` sections as needed

---

## Investigations

Incident and debugging writeups in `~/.vault/investigations/`. Use `_templates/investigation.md`.

Filename: `<env-or-service>-<short-slug>-investigation.md`

---

## Personal (optional)

Non-technical folders that live beside the knowledge base. Their pages use their own
templates, not the wiki page template, and are listed under **Personal** in INDEX.md. Other
personal folders are fine too: list them there.

### Job application
When given a job posting:
1. Screen it against `job-search/criteria.md` non-negotiables; if it fails, say why and stop
2. Create `job-search/applications/<company>-<role>.md` from `_templates/application.md`, pasting the full posting and filling the fit score
3. Pick the closest variant in `job-search/resumes/`, then tailor it using only facts from `job-search/master-resume.md`. Never invent experience or metrics
4. Write the tailored resume to `job-search/applications/<company>-<role>/resume.md`. If `job-search/templates/` has a build script, render the PDF with it and check it is at most 2 pages and its text extracts cleanly
5. Draft the cover letter and outreach message following `job-search/cover-letter-playbook.md`, if it exists
6. Add a row to `job-search/tracker.md`
7. Once the process reaches an interview, create the guide (below) and link it from the tracker

Resume rules: single column, standard headings (Summary, Experience, Projects, Skills, Education), no tables or graphics, mirror the posting's exact keywords, quantified bullets, 1–2 pages.

### Interview prep
1. Create `interviews/<company>-interview-guide.md` from `_templates/interview-guide.md`
2. Keep one guide per company; update it as the process moves through stages rather than creating new pages
3. Fill in the Post-Interview Notes section after each round

---

## Health Checks (Lint)

When asked to lint the wiki, check for:
1. **Staleness** — pages not updated in 60+ days relative to repo activity
2. **Contradictions** — information that conflicts across pages
3. **Orphans** — pages not referenced in INDEX.md
4. **Broken links** — `[[links]]` pointing to non-existent pages
5. **Missing pages** — systems or repos Claude has worked in that have no page
6. **Open questions** — unresolved items that could now be answered
7. **Log bloat** — log.md over ~150 lines; archive entries older than 3 months
