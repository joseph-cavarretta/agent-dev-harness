CLAUDE_DIR := $(HOME)/.claude
CURSOR_DIR := $(HOME)/.cursor
VAULT_DIR := $(HOME)/.vault
BIN_DIR := $(HOME)/.local/bin
SETTINGS := $(CLAUDE_DIR)/settings.json
OS := $(shell uname -s)
VALE_STYLES_DIR := $(HOME)/Library/Application Support/vale/styles
ifeq ($(OS),Linux)
VALE_STYLES_DIR := $(HOME)/.local/share/vale/styles
endif

.PHONY: install install-vault vault-init install-tools install-prose install-cursor test-tools test-hooks test-prose new-project mcp uninstall

# Symlink the base instructions and hooks, then merge the managed settings keys into
# ~/.claude/settings.json. A merge rather than a symlink: Claude Code writes /model and theme
# choices into settings.json, which would otherwise dirty this repo.
install:
	@mkdir -p "$(CLAUDE_DIR)/hooks"
	@ln -sfn "$(CURDIR)/claude/CLAUDE.base.md" "$(CLAUDE_DIR)/CLAUDE.base.md"
	@for hook in $(CURDIR)/claude/hooks/*.py; do ln -sfn "$$hook" "$(CLAUDE_DIR)/hooks/$$(basename $$hook)"; done
	@$(MAKE) --no-print-directory merge-settings SOURCE=$(CURDIR)/claude/settings.json
	@echo "Installed. Make sure ~/.claude/CLAUDE.md starts with: @CLAUDE.base.md"

# Optional vault module: only installs when ~/.vault exists. Each step is its own recipe line:
# make runs any line containing $(MAKE) even under -n, so side effects must not share a line with it.
install-vault:
ifeq ($(wildcard $(VAULT_DIR)/.),)
	@echo "No $(VAULT_DIR) — skipping vault module (run make vault-init first)"
else
	@mkdir -p "$(CLAUDE_DIR)/hooks"
	@ln -sfn "$(CURDIR)/vault/CLAUDE.vault.md" "$(CLAUDE_DIR)/CLAUDE.vault.md"
	@for hook in $(CURDIR)/vault/hooks/*.py; do ln -sfn "$$hook" "$(CLAUDE_DIR)/hooks/$$(basename $$hook)"; done
	@$(MAKE) --no-print-directory merge-settings SOURCE=$(CURDIR)/vault/settings.json
	@echo "Vault module installed. Add this line to ~/.claude/CLAUDE.md after the base import: @CLAUDE.vault.md"
endif

# Bootstrap a fresh knowledge base from the scaffold. Never overwrites an existing vault.
vault-init:
	@if [ -e "$(VAULT_DIR)" ]; then \
		echo "$(VAULT_DIR) already exists — not overwriting"; \
	else \
		cp -r "$(CURDIR)/vault/scaffold" "$(VAULT_DIR)" && echo "Created $(VAULT_DIR)"; \
	fi

# Link the ah-* scripts onto PATH. The tools-index hook (from `make install`) lists them
# in every session.
install-tools:
	@mkdir -p "$(BIN_DIR)"
	@for script in $(CURDIR)/tools/bin/ah-*; do [ -e "$$script" ] || continue; ln -sfn "$$script" "$(BIN_DIR)/$$(basename $$script)"; done
	@echo "Tools installed. Make sure $(BIN_DIR) is on PATH."

# Link prose styleguide, Vale configuration, and House style rules.
install-prose:
	@mkdir -p "$(BIN_DIR)"
	@ln -sfn "$(CURDIR)/prose-styleguide/vale-lint" "$(BIN_DIR)/vale-lint"
	@ln -sfn "$(CURDIR)/prose-styleguide/.vale.ini" "$(HOME)/.vale.ini"
	@mkdir -p "$(VALE_STYLES_DIR)"
	@ln -sfn "$(CURDIR)/prose-styleguide/styles/House" "$(VALE_STYLES_DIR)/House"
	@if command -v vale >/dev/null 2>&1; then vale sync; fi
	@echo "Prose styleguide and Vale installed."

# Link Cursor rules and completion-gate hooks into ~/.cursor.
install-cursor:
	@mkdir -p "$(CURSOR_DIR)/hooks" "$(CURSOR_DIR)/rules"
	@for hook in $(CURDIR)/cursor/hooks/*.py; do [ -e "$$hook" ] || continue; ln -sfn "$$hook" "$(CURSOR_DIR)/hooks/$$(basename $$hook)"; done
	@for rule in $(CURDIR)/cursor/rules/*.mdc; do [ -e "$$rule" ] || continue; ln -sfn "$$rule" "$(CURSOR_DIR)/rules/$$(basename $$rule)"; done
	@echo "Cursor hooks and rules linked into $(CURSOR_DIR)."

test-tools:
	@uv run --no-project --with pytest pytest -q "$(CURDIR)/tools/tests"

test-hooks:
	@uv run --no-project --with pytest pytest -q "$(CURDIR)/claude/tests"

test-prose:
	@$(CURDIR)/prose-styleguide/vale-lint $(CURDIR)/prose-styleguide/prose-styleguide.md

# New Python project from templates/python-project, to the styleguide's layout. Pass any
# copier answer with DATA, e.g. DATA='--data description="Order sync"'.
new-project:
	@[ -n "$(DEST)" ] || { echo "usage: make new-project DEST=~/dev/<name> [DATA='--data key=value']"; exit 1; }
	@[ ! -e "$(DEST)" ] || { echo "$(DEST) already exists"; exit 1; }
	@uvx copier copy --quiet --defaults --data project_name=$$(basename "$(DEST)") $(DATA) "$(CURDIR)/templates/python-project" "$(DEST)"
	@cd "$(DEST)" && git init -q && uv sync -q
	@echo "Created $(DEST). Verify with: ah-check $(DEST)"

mcp:
	@cd "$(CURDIR)/mcp/delegate" && uv sync
	@echo "Register the server in ~/.claude.json under mcpServers:"
	@echo "  \"delegate\": {\"command\": \"uv\", \"args\": [\"run\", \"--directory\", \"$(CURDIR)/mcp/delegate\", \"delegate-mcp\"]}"

# Removes symlinks that point into this repo. Leaves settings.json alone.
uninstall:
	@for link in "$(CLAUDE_DIR)"/CLAUDE.base.md "$(CLAUDE_DIR)"/CLAUDE.vault.md "$(CLAUDE_DIR)"/hooks/*.py \
		"$(CURSOR_DIR)"/hooks/*.py "$(CURSOR_DIR)"/rules/*.mdc \
		"$(BIN_DIR)"/ah-* "$(BIN_DIR)"/vale-lint "$(HOME)/.vale.ini" "$(VALE_STYLES_DIR)/House"; do \
		if [ -L "$$link" ] && readlink "$$link" | grep -q "^$(CURDIR)/"; then rm "$$link" && echo "removed $$link"; fi; \
	done

.PHONY: merge-settings
merge-settings:
	@mkdir -p "$(CLAUDE_DIR)"
	@if [ -f "$(SETTINGS)" ]; then cp "$(SETTINGS)" "$(SETTINGS).bak"; else echo "{}" > "$(SETTINGS).bak"; fi
	@jq -s -f "$(CURDIR)/scripts/merge-settings.jq" "$(SETTINGS).bak" "$(SOURCE)" > "$(SETTINGS).tmp"
	@rm -f "$(SETTINGS)" && mv "$(SETTINGS).tmp" "$(SETTINGS)"
	@echo "Merged $(notdir $(SOURCE)) into $(SETTINGS) (previous version: settings.json.bak)"
