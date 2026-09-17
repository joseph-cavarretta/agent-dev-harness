CLAUDE_DIR := $(HOME)/.claude
VAULT_DIR := $(HOME)/.vault
SETTINGS := $(CLAUDE_DIR)/settings.json

.PHONY: install install-vault vault-init mcp uninstall

# Symlink the base instructions and hooks, then merge the managed settings keys into
# ~/.claude/settings.json. A merge rather than a symlink: Claude Code writes /model and theme
# choices into settings.json, which would otherwise dirty this repo.
install:
	@mkdir -p "$(CLAUDE_DIR)/hooks"
	@ln -sfn "$(CURDIR)/claude/CLAUDE.base.md" "$(CLAUDE_DIR)/CLAUDE.base.md"
	@for hook in $(CURDIR)/claude/hooks/*.py; do ln -sfn "$$hook" "$(CLAUDE_DIR)/hooks/$$(basename $$hook)"; done
	@$(MAKE) --no-print-directory merge-settings SOURCE=$(CURDIR)/claude/settings.json
	@echo "Installed. Make sure ~/.claude/CLAUDE.md starts with: @CLAUDE.base.md"

# Optional vault module: only installs when ~/.vault exists.
install-vault:
	@if [ ! -d "$(VAULT_DIR)" ]; then echo "No $(VAULT_DIR) — skipping vault module (run make vault-init first)"; exit 0; fi; \
	mkdir -p "$(CLAUDE_DIR)/hooks"; \
	ln -sfn "$(CURDIR)/vault/CLAUDE.vault.md" "$(CLAUDE_DIR)/CLAUDE.vault.md"; \
	for hook in $(CURDIR)/vault/hooks/*.py; do ln -sfn "$$hook" "$(CLAUDE_DIR)/hooks/$$(basename $$hook)"; done; \
	$(MAKE) --no-print-directory merge-settings SOURCE=$(CURDIR)/vault/settings.json; \
	echo "Vault module installed. Add this line to ~/.claude/CLAUDE.md after the base import: @CLAUDE.vault.md"

# Bootstrap a fresh knowledge base from the scaffold. Never overwrites an existing vault.
vault-init:
	@if [ -e "$(VAULT_DIR)" ]; then \
		echo "$(VAULT_DIR) already exists — not overwriting"; \
	else \
		cp -r "$(CURDIR)/vault/scaffold" "$(VAULT_DIR)" && echo "Created $(VAULT_DIR)"; \
	fi

mcp:
	@cd "$(CURDIR)/mcp/delegate" && uv sync
	@echo "Register the server in ~/.claude.json under mcpServers:"
	@echo "  \"delegate\": {\"command\": \"uv\", \"args\": [\"run\", \"--directory\", \"$(CURDIR)/mcp/delegate\", \"delegate-mcp\"]}"

# Removes symlinks that point into this repo. Leaves settings.json alone.
uninstall:
	@for link in "$(CLAUDE_DIR)"/CLAUDE.base.md "$(CLAUDE_DIR)"/CLAUDE.vault.md "$(CLAUDE_DIR)"/hooks/*.py; do \
		if [ -L "$$link" ] && readlink "$$link" | grep -q "^$(CURDIR)/"; then rm "$$link" && echo "removed $$link"; fi; \
	done

.PHONY: merge-settings
merge-settings:
	@mkdir -p "$(CLAUDE_DIR)"
	@if [ -f "$(SETTINGS)" ]; then cp "$(SETTINGS)" "$(SETTINGS).bak"; else echo "{}" > "$(SETTINGS).bak"; fi
	@jq -s -f "$(CURDIR)/scripts/merge-settings.jq" "$(SETTINGS).bak" "$(SOURCE)" > "$(SETTINGS).tmp"
	@rm -f "$(SETTINGS)" && mv "$(SETTINGS).tmp" "$(SETTINGS)"
	@echo "Merged $(notdir $(SOURCE)) into $(SETTINGS) (previous version: settings.json.bak)"
