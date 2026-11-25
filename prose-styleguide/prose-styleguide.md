# Prose styleguide and technical writing

The technical documentation and prose standard for repository docs, vault notes,
architecture records, TRDs, and PRDs.

---

## The enforcement split

As with Python code and Ruff, this system enforces documentation standards through a
strict division:

- Prose linter (Vale) provides deterministic, zero-token enforcement of sentence-case
  headings (`House.Headings`), no bold lead-in list labels (`House.BoldBullet`), no
  semicolon-ended list items (`House.ListPunctuation`), avoidance of editorial
  first-person plural (`Google.We`), present tense (`Google.Will`), descriptive link
  anchor text (`House.Links`), filler phrases (`House.Filler`), `zero` as a quantifier
  (`House.ZeroQuantifier`, `House.ZeroQuantifierAdj`), and plain-English word
  substitutions (`House.WordList`).
- Agent prompts (`CLAUDE.base.md`) provide guidance on audience,
  clarity, tone, active voice, Oxford commas, positive framing, and list structure.

Anything a mechanical linter can check belongs in configuration, not in agent prompt tokens.

---

## Scope and exclusions

Prose linting targets Markdown documents (`*.md`, `*.mdx`) only. It deliberately does
not run against code or docstrings:

1. Code comments are short, terse notes rather than prose. Running a prose linter on them produces constant false alarms.
2. Python docstrings are checked by Ruff and `docstring_length.py`, which caps lines, prevents restating signatures, and forbids `Args:` / `Returns:` blocks.
3. Code files contain variable names, SQL fragments, and types that trigger false positives under English prose dictionaries.
4. Generated indices, logs, and agent prompts (`INDEX.md`, `log.md`, `CHANGELOG.md`, `CLAUDE*.md`, `AGENTS.md`, `SKILL.md`, `raw/`, `archive/`, `_templates/`, and `.github/`) are skipped by default.

---

## Voice and perspective

- Prefer active voice over passive voice: state who or what performs the action ("The worker polls Redis", not "Redis is polled by the worker").
- Use second person ("you") or imperative commands ("Run `make test`", "Configure the service").
- Never use editorial first-person plural: avoid `we`, `let's`, `our`, and `us`. Replace `we review the schema` with `review the schema` or `this section covers the schema`. First-person singular (`I`, `my`) is allowed in personal notes and READMEs.
- Use present tense to describe how the system behaves right now ("The endpoint returns 404"). Future tense (`will`) is permitted in forward-looking `plans/` and `proposals/`.
- Frame instructions positively: state what to do rather than what to avoid when possible.

---

## Structure and scannability

### Headings and summaries

- Use sentence-case capitalization (`## System topology`, `## ArgoCD rollout system`, not `## System Topology`).
- Use `Summary` or `TLDR` as the section heading rather than `Executive Summary` or `BLUF`.

### Lists and tables

- Do not start list items with bold lead-in labels (`- **Title:** explanation`, `- **Title.** explanation`, or `- **Title** - explanation`). Group related points under `###` or `####` subheadings with direct bullets, or use a table (`House.BoldBullet`).
- End full-sentence list items with a period (or omit punctuation on short fragments); never end list items with semicolons (`;`, `; and`) (`House.ListPunctuation`).
- Use numbered lists strictly for sequential, chronological instructions, and bulleted lists for unordered items or parallel concepts.
- Maintain parallel grammatical structure across list items (for example, start each item with an imperative verb).
- Use Oxford (serial) commas in all lists of three or more items.

### Links and punctuation

- Use descriptive link anchor text naming the target. Never use `[here](...)`, `[click here](...)`, or `[link](...)`. Keep Obsidian `[[wiki/path]]` format for internal vault links.
- Avoid overusing AI-style em-dashes; prefer commas, colons, parentheses, or separate sentences (`House.EmDash` runs at `suggestion` level).

---

## Word choice and plain language

Replace jargon and filler with plain English (`House.WordList` and `House.Filler`):

| Jargon / Filler | Replacement |
|---|---|
| `hydrate` | fill in / look up |
| `wire format` | response shape |
| `by construction` | structurally |
| `fail-open` | slip through silently |
| `canonical` | stable |
| `primitive` | feature / fallback |
| `well-formedness` | consistency |
| `obligations` | what it must do |
| `ensure` | verify / make sure |
| `kill` | stop / terminate |
| `utilize` / `leverage` | use |
| `in order to` | to |
| `Executive Summary` / `BLUF` | Summary / TLDR |
| `note that` / `it is worth noting` | *(cut filler phrase)* |
| `zero <noun>` (quantifier) | no / none / without any |

Keep precise technical terms that carry specific meaning (BM25, kNN, denylist, chunk_id, NLI, OOXML, etc.).

---

## Code and formatting in prose

- Use backticks for file paths, commands, parameters, class names, HTTP methods, and identifiers.
- Put punctuation outside code tags unless the punctuation is part of the code itself.
- Code blocks (```) and inline code (`` `code` ``) inside Markdown files are excluded from style checks via `IgnoredScopes = code, tt, frontmatter`.

---

## Running the linter

```bash
# Check changed Markdown files in current git repository
vale-lint

# Check specific files or directories
vale-lint path/to/doc.md
vale-lint ~/.vault/wiki/patterns/

# Show suggestions (including passive voice and em-dash nudges)
vale-lint --min-alert-level=suggestion path/to/doc.md
```
