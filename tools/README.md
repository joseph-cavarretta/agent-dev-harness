# tools

Scripts the agent runs through the shell instead of improvising commands or reading raw output. The win is context: a script does the fetching and filtering, and only its summary reaches the model.

## Conventions

Every script in `bin/` must:

- Be named `ah-<name>`. The prefix is what `claude/settings.json` allows (`Bash(ah-*)`) and what usage stats key on.
- Be **read-only**. The allow rule runs these without a prompt, so anything that changes state belongs elsewhere.
- Support `--help`, exiting 0.
- Print a summary by default, not a dump: counts, top N, one line per item. Take flags such as `--limit` to widen or narrow it.
- Print one of two shapes: aligned text for reading, or JSON lines under `--json` for piping into another script or `jq`.
- Exit non-zero on failure, with the reason on stderr.
- Have a `# summary:` line in its first 20 lines: what it returns and when to use it. Wrap long summaries onto following lines that start with `#   `. The `tools-index` hook injects it into every session, so write it as a trigger ("Use instead of ..."). The contract test checks it exists and stays short.

## Adding a script

1. Write `bin/ah-<name>` and `chmod +x` it.
2. Add its `# summary:` line.
3. `make test-tools`, then `make install-tools` to link it onto your PATH.
