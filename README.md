# antigravity-mcp

FastMCP server that lets Claude Code delegate bulk work to the Antigravity CLI (`agy`), then proves the result instead of trusting it.

Claude orchestrates and reviews; `agy` does the volume. The rules deciding *when* to reach for it live in `~/.claude/CLAUDE.base.md`.

## The premise

`agy` is cheap to run and unreliable about its own output — it has claimed success on work that failed and reported errors on work that passed. Its self-report is never the evidence.

Everything here follows from that:

- Work a command can check is delegated with a `verify_command`, and **this server runs that command itself**.
- Work consumed programmatically is delegated with an `output_schema`, so the result is validated rather than parsed out of prose.
- Work that can only be judged by reading carries its full review cost, and usually isn't worth delegating.

## Tools

| Tool | Use for | Evidence |
|---|---|---|
| `delegate_task` | Bulk reading, multi-repo sweeps, extraction | `output_schema`, when supplied |
| `delegate_code_draft` | Writing a file to a spec | `verify_command` |
| `delegate_vault_document` | Long vault prose from facts you supply, following `~/.vault/_templates/` | none — you review all of it |
| `refine_delegation` | Corrections to an earlier call, via its `conversation_id` | `verify_command`, when supplied |
| `delegation_stats` | Whether delegating is actually paying off | — |

Pass file *paths*, not file contents: `agy` has its own read tools and will read them itself.

## The verify loop

`delegate_code_draft` and `refine_delegation` accept a `verify_command`. Once `agy` returns:

1. The server runs the command itself, from `verify_directory`.
2. On failure, the output is fed back to `agy` over the same `conversation_id`.
3. That repeats up to `max_verify_rounds` (default 4).
4. The response reports the observed exit code, and the review checklist it returns differs depending on whether the check actually passed.

The loop lives here rather than in the prompt because `agy`'s shell starts in a scratch directory and will report a passing run it never made. Only this side sees the real exit code, so only this side can decide whether to iterate.

## Setup

Requires the `agy` binary (default `~/.local/bin/agy`) and [uv](https://docs.astral.sh/uv/).

```bash
make antigravity-mcp        # from the dotfiles root; symlinks this package into ~/dev
cd ~/dev/antigravity-mcp
uv sync
```

Register the server in `~/.claude.json`:

```json
{
  "mcpServers": {
    "antigravity": {
      "command": "uv",
      "args": ["run", "--directory", "/home/you/dev/antigravity-mcp", "antigravity-mcp"]
    }
  }
}
```

The path must be absolute — `~` is not expanded here. The `claude` stow package already allows
`Bash(agy *)` and `mcp__antigravity__*`.

## Configuration

`Settings` is a `BaseSettings` model. Every field is overridable with an `ANTIGRAVITY_MCP_` prefixed
environment variable, e.g. `ANTIGRAVITY_MCP_DEFAULT_EFFORT=low`.

| Setting | Default |
|---|---|
| `agy_bin_path` | `~/.local/bin/agy` |
| `default_model` | `gemini-3.7-flash` |
| `default_effort` | `high` |
| `default_timeout_seconds` | `300` |
| `timeout_grace_seconds` | `30` |
| `verify_timeout_seconds` | `300` |
| `max_verify_rounds` | `4` |
| `vault_path` | `~/.vault` |
| `vault_templates_path` | `~/.vault/_templates` |
| `dev_path` | `~/dev` |
| `dangerously_skip_permissions` | `true` |
| `log_path` | `~/.claude/antigravity-delegations.jsonl` |

`timeout_grace_seconds` is deliberate: the subprocess gets a longer leash than `agy`'s own
`--print-timeout` so `agy` times out first and its error message survives.

`dangerously_skip_permissions` defaults on, so `agy` runs auto-approved and can write anywhere under
`~/dev` and `~/.vault`. Scope `working_directory` to the narrowest path that works, and keep secrets
and IaC out of delegations entirely.

## Logging

Every delegation appends one JSONL record to `log_path`: timestamp, tool, target file, `agy`'s
claimed success, the verified result, verify rounds, conversation id, duration, and token counts.
Bookkeeping failures are swallowed — they never break a delegation.

`delegation_stats` reads that log back and reports the correction rate and, most usefully, how often
`agy`'s self-report disagreed with the observed check.

## Development

```bash
uv run pytest
```

`AgyRunner` and `ShellVerifier` are injected into `create_server()` behind Protocols, so every tool
is testable without invoking `agy` or running a real shell command.
