# agent-dev-harness

The standards, guardrails, and tools I use to for AI coding agents. Installs into Claude Code.

## What's here

| Path | What it does |
|---|---|
| `claude/CLAUDE.base.md` | Shared instructions: code, testing, git, writing style, and when to delegate |
| `claude/settings.json` | Permission allow/deny baseline and hook wiring |
| `claude/hooks/` | `secret-scanner` (blocks writes containing keys or tokens), `git-commit-guard` (rejects commit messages off the `type(scope): description` format), `audit-log` (logs every shell command), `precompact-snapshot` (keeps in-progress work through context compaction) |
| `python-styleguide/` | The Python style guide, `ruff-base.toml` (strict lint and format baseline repos extend), and `docstring_length.py` (flags sprawling docstrings) |
| `mcp/delegate/` | MCP server that hands bulk reading and code drafting to a worker agent CLI and verifies the result. See its [README](mcp/delegate/README.md) |
| `vault/` | Optional module for a Markdown knowledge base: instructions, two hooks, and an empty scaffold |

## Install

Requires [Claude Code](https://docs.claude.com/en/docs/claude-code), `jq`, and [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:joseph-cavarretta/agent-dev-harness.git ~/dev/agent-dev-harness
cd ~/dev/agent-dev-harness
make install
```

`make install` symlinks `CLAUDE.base.md` and the hooks into `~/.claude/`, then merges `claude/settings.json` into `~/.claude/settings.json`. It merges rather than symlinks because Claude Code writes model and theme choices into that file. Objects merge, permission and hook lists are combined, and your own keys are kept; the previous file is saved as `settings.json.bak`. Removing a rule here does not remove it from an existing install.

Then start `~/.claude/CLAUDE.md` with the import, and add anything machine-specific below it:

```markdown
@CLAUDE.base.md
```

Optional targets:

```bash
make mcp            # uv sync the delegation server and print its ~/.claude.json entry
make vault-init     # create ~/.vault from the scaffold (never overwrites)
make install-vault  # vault instructions, hooks, and settings; skipped without ~/.vault
make uninstall      # remove symlinks into this repo (settings.json is left alone)
```

To use the ruff baseline in another repo, extend it rather than copying it:

```toml
[tool.ruff]
extend = "../agent-dev-harness/python-styleguide/ruff-base.toml"
```

## Development

```bash
cd mcp/delegate && uv run pytest
```
