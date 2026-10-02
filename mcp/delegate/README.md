# delegate-mcp

MCP server that lets Claude Code delegate bulk work to a worker agent CLI, then proves the result instead of trusting it. Runners sit behind `WorkerRunnerProtocol`, so the tools don't know which CLI does the work. Supporting another CLI means writing one new runner and passing it to `create_server()`.

Claude orchestrates and reviews; the worker does the volume. The rules deciding *when* to reach for it live in `~/.claude/CLAUDE.base.md`.

## The premise

The worker is cheap to run and unreliable about its own output — it has claimed success on work that failed and reported errors on work that passed. Its self-report is never the evidence.

Everything here follows from that:

- Work a command can check is delegated with a `verify_command`, and **this server runs that command itself**.
- Work consumed programmatically is delegated with an `output_schema`, so the result is validated rather than parsed out of prose.
- Work that can only be judged by reading carries its full review cost, and usually isn't worth delegating.

## Tools

| Tool | Use for | Evidence |
|---|---|---|
| `delegate_task` | Bulk reading, multi-repo sweeps, extraction | `output_schema`, when supplied |
| `delegate_code_draft` | Writing a file to a spec | `verify_command` |
| `delegate_vault_document` | Long vault prose from facts you supply, following `~/.vault/_templates/`. Only offered when `vault_path` exists | none — you review all of it |
| `refine_delegation` | Corrections to an earlier call, via its `conversation_id` | `verify_command`, when supplied |
| `delegation_stats` | Whether delegating is actually paying off | — |

Pass file *paths*, not file contents: the worker has its own read tools and will read them itself.

## The verify loop

`delegate_code_draft` and `refine_delegation` accept a `verify_command`. Once the worker returns:

1. The server runs the command itself, from `verify_directory`.
2. On failure, the output is fed back to the worker over the same `conversation_id`.
3. That repeats up to `max_verify_rounds` (default 4).
4. The response reports the observed exit code, and the review checklist it returns differs depending on whether the check actually passed.

The loop lives here rather than in the prompt because the worker's shell may start in a scratch directory and will report a passing run it never made. Only this side sees the real exit code, so only this side can decide whether to iterate.

## Setup

Requires the worker CLI binary (set `worker_bin_path`) and [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:joseph-cavarretta/agent-dev-harness.git ~/dev/agent-dev-harness
cd ~/dev/agent-dev-harness
make mcp        # uv sync + prints the registration snippet
```

Register the server in `~/.claude.json`:

```json
{
  "mcpServers": {
    "delegate": {
      "command": "uv",
      "args": ["run", "--directory", "/home/you/dev/agent-dev-harness/mcp/delegate", "delegate-mcp"]
    }
  }
}
```

The path must be absolute — `~` is not expanded here. Allow the worker binary and
`mcp__delegate__*` in your Claude Code permissions (the harness `claude/settings.json` already does).

## Configuration

`Settings` is a `BaseSettings` model. Every field is overridable with a `DELEGATE_MCP_` prefixed
environment variable, e.g. `DELEGATE_MCP_DEFAULT_EFFORT=low`.

| Setting | Default |
|---|---|
| `worker_bin_path` | the worker CLI under `~/.local/bin` |
| `default_model` | the worker's fast default model |
| `default_effort` | `high` |
| `default_timeout_seconds` | `300` |
| `timeout_grace_seconds` | `30` |
| `verify_timeout_seconds` | `300` |
| `max_verify_rounds` | `4` |
| `vault_path` | `~/.vault` |
| `vault_templates_path` | `~/.vault/_templates` |
| `dev_path` | `~/dev` |
| `dangerously_skip_permissions` | `true` |
| `log_path` | `~/.claude/delegations.jsonl` |

`timeout_grace_seconds` is deliberate: the subprocess gets a longer leash than the worker's own
timeout so the worker times out first and its error message survives.

`dangerously_skip_permissions` defaults on, so the worker runs auto-approved and can write anywhere under
`~/dev` and `~/.vault`. Scope `working_directory` to the narrowest path that works, and keep secrets
and IaC out of delegations entirely.

## Logging

Every delegation appends one JSONL record to `log_path`: timestamp, tool, target file, the worker's
claimed success, the verified result, verify rounds, conversation id, duration, and token counts.
Bookkeeping failures are swallowed — they never break a delegation.

`delegation_stats` reads that log back and reports the correction rate and, most usefully, how often
the worker's self-report disagreed with the observed check.

## Development

```bash
uv run pytest
```

The runner and `ShellVerifier` are injected into `create_server()` behind Protocols, so every tool
is testable without invoking a worker CLI or running a real shell command.
