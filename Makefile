# ==============================================================================
# NetBird self-hosted IaC - Makefile wrapper
# ==============================================================================
# Entry points around ansible-playbook / ansible-lint. Run `make help` for the
# target list. Override HOST=... (single host), TAGS=... (focused run).

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Fixed paths (not operator knobs): the playbooks and inventory are part of the
# repo layout. Non-mainstream cases can call ansible directly.
PLAYBOOK      := playbooks/site.yml
INVENTORY     := inventory/hosts.yml
INVENTORY_DIR := inventory

# Command-line inputs (set at invocation, e.g. `make restore FROM=<dir>`).
TAGS ?=
HOST ?=
FROM ?=

# Ansible Vault password file (outside the repo), exported under Ansible's own
# env-var name so every ansible-* invocation picks it up.
export ANSIBLE_VAULT_PASSWORD_FILE := $(HOME)/.config/projects/netbird-iac/ansible_vault_password

# Unified operator hint, printed only when a vault command cannot decrypt a
# file (the vault password is missing or does not match).
VAULT_PASSWORD_HINT := ERROR: Ansible Vault cannot decrypt this file - the password in $(ANSIBLE_VAULT_PASSWORD_FILE) is missing or incorrect. Restore the original password, or re-encrypt the vault file with the current one.

# sshpass is needed ONLY for the `host-bootstrap` password probe. It is ensured
# by the internal `ensure-sshpass` target (invoked by `install`): installed with
# passwordless apt-get when available, otherwise rootless into
# ~/.local/bin/sshpass; a failure is fatal (install it manually and re-run).
# Key-only bootstrap does not need it, and steady-state Ansible password auth
# uses ssh_askpass, not sshpass.
SSHPASS_BIN   := $(HOME)/.local/bin/sshpass

.PHONY: help
help: ## Show targets (variables are overridable per target, e.g. make deploy TAGS=...)
	@printf '\nUsage: make <target> [VAR=value ...]\n'
	@awk 'BEGIN {FS = ":.*?## "} \
		/^[a-zA-Z0-9_-]+:.*?## / { printf "  \033[36m%-23s\033[0m %s\n", $$1, $$2 }' \
		$(MAKEFILE_LIST)
	@printf '\n'

.PHONY: install
install: ensure-sshpass ## Install the pinned toolchain, Galaxy collections, and sshpass
	@if command -v mise >/dev/null 2>&1; then mise install; \
	elif command -v asdf >/dev/null 2>&1; then asdf install; \
	else echo "Neither mise nor asdf found; install one, or ensure ansible-core 2.19.x is on PATH." >&2; exit 1; fi
	ansible-galaxy install -r requirements.yml

# (internal) ensure sshpass: passwordless apt-get when available, otherwise a
# rootless install into ~/.local/bin. A failure is fatal — no silent fallback.
ensure-sshpass:
	@set -e; \
	if command -v sshpass >/dev/null 2>&1 || [ -x "$(SSHPASS_BIN)" ]; then \
		echo "sshpass: present"; \
	elif sudo -n true >/dev/null 2>&1; then \
		echo "sshpass: installing via sudo apt-get..."; \
		sudo -n apt-get install -y sshpass; \
	else \
		echo "sshpass: installing rootless into $(dir $(SSHPASS_BIN))..."; \
		if ! command -v apt-get >/dev/null 2>&1 || ! command -v dpkg-deb >/dev/null 2>&1; then \
			echo "Cannot auto-install sshpass (apt-get/dpkg-deb not found)." >&2; \
			echo "Install sshpass manually, or use key-only bootstrap credentials." >&2; \
			exit 1; \
		fi; \
		tmp=$$(mktemp -d); \
		trap 'rm -rf "$$tmp"' EXIT; \
		cd "$$tmp"; \
		apt-get download sshpass >/dev/null 2>&1; \
		dpkg-deb -x sshpass_*.deb root; \
		mkdir -p "$(dir $(SSHPASS_BIN))"; \
		install -m 0755 root/usr/bin/sshpass "$(SSHPASS_BIN)"; \
		echo "sshpass installed: $(SSHPASS_BIN)"; \
	fi

.PHONY: host-init
host-init: vault-init ## Scaffold host_vars/<HOST> from the example/ template
	@if [ -z "$(HOST)" ]; then echo "Usage: make host-init HOST=<hostname>" >&2; exit 1; fi
	@if [ -e "$(INVENTORY)" ]; then :; else cp inventory/hosts.yml.example $(INVENTORY); echo "Created $(INVENTORY) from example"; fi
	install -d -m 0700 $(INVENTORY_DIR)/host_vars/$(HOST)
	if [ ! -e $(INVENTORY_DIR)/host_vars/$(HOST)/main.yml ]; then cp $(INVENTORY_DIR)/host_vars/example/main.yml $(INVENTORY_DIR)/host_vars/$(HOST)/main.yml; fi
	chmod 0644 $(INVENTORY_DIR)/host_vars/$(HOST)/main.yml
	if [ ! -e $(INVENTORY_DIR)/host_vars/$(HOST)/vault.yml ]; then cp $(INVENTORY_DIR)/host_vars/example/vault.yml.example $(INVENTORY_DIR)/host_vars/$(HOST)/vault.yml; fi
	@if grep -q 'ANSIBLE_VAULT' $(INVENTORY_DIR)/host_vars/$(HOST)/vault.yml; then :; else \
		echo "Encrypting $(INVENTORY_DIR)/host_vars/$(HOST)/vault.yml..."; \
		ansible-vault encrypt $(INVENTORY_DIR)/host_vars/$(HOST)/vault.yml; \
	fi
	chmod 0600 $(INVENTORY_DIR)/host_vars/$(HOST)/vault.yml
	@echo "Scaffolded $(INVENTORY_DIR)/host_vars/$(HOST)/ (edit main.yml; use 'make vault-edit HOST=$(HOST)' for the encrypted vault.yml)"

.PHONY: host-bootstrap
host-bootstrap: vault-init ## Host init only: service account, Docker, mirrors (bootstrap.yml)
	ansible-playbook -i $(INVENTORY) playbooks/bootstrap.yml

.PHONY: vault-init
vault-init: ## Create the Ansible Vault password file (if missing) and preflight it
	@mkdir -p $(dir $(ANSIBLE_VAULT_PASSWORD_FILE))
	@if [ ! -s "$(ANSIBLE_VAULT_PASSWORD_FILE)" ]; then \
		openssl rand -base64 32 > "$(ANSIBLE_VAULT_PASSWORD_FILE)"; \
		chmod 600 "$(ANSIBLE_VAULT_PASSWORD_FILE)"; \
		echo "vault password generated: $(ANSIBLE_VAULT_PASSWORD_FILE) (BACK IT UP in a password manager)"; \
	fi
	@test "$$(wc -c < "$(ANSIBLE_VAULT_PASSWORD_FILE)")" -ge 44 || { echo "ERROR: vault password too weak"; exit 1; }
	@f=""; \
	for c in $$(find "$(INVENTORY_DIR)" -type f -name 'vault*.yml' 2>/dev/null); do \
		if head -c 16 "$$c" | grep -q 'ANSIBLE_VAULT'; then f="$$c"; break; fi; \
	done; \
	if [ -n "$$f" ] && command -v ansible-vault >/dev/null 2>&1; then \
		ansible-vault view "$$f" >/dev/null 2>&1 \
			|| { printf '%s\n' "$(VAULT_PASSWORD_HINT)" >&2; exit 1; }; \
	fi

.PHONY: vault-edit
vault-edit: vault-init ## Edit vault.yml; HOST optional if single-host
	@host="$(HOST)"; \
	if [ -z "$$host" ]; then \
		host="$$(ansible-inventory -i $(INVENTORY) --list 2>/dev/null \
			| python3 -c 'import json,sys; h=list(json.load(sys.stdin).get("_meta",{}).get("hostvars",{})); print(h[0] if len(h)==1 else "")')"; \
	fi; \
	if [ -z "$$host" ]; then \
		echo "Usage: make vault-edit HOST=<hostname>" >&2; exit 1; \
	fi; \
	p="$(INVENTORY_DIR)/host_vars/$$host/vault.yml"; \
	if [ ! -f "$$p" ]; then echo "No such vault file: $$p" >&2; exit 1; fi; \
	if grep -q 'ANSIBLE_VAULT' "$$p"; then :; else \
		echo "Encrypting plaintext $$p before editing..."; \
		ansible-vault encrypt "$$p"; \
	fi; \
	ansible-vault edit "$$p"

.PHONY: vault-view
vault-view: vault-init ## Print vault.yml + vault_managed.yml (decrypted); HOST optional if single-host
	@host="$(HOST)"; \
	if [ -z "$$host" ]; then \
		host="$$(ansible-inventory -i $(INVENTORY) --list 2>/dev/null \
			| python3 -c 'import json,sys; h=list(json.load(sys.stdin).get("_meta",{}).get("hostvars",{})); print(h[0] if len(h)==1 else "")')"; \
	fi; \
	if [ -z "$$host" ]; then \
		echo "Usage: make vault-view HOST=<hostname> (required when the inventory has no single host)" >&2; exit 1; \
	fi; \
	for f in vault.yml vault_managed.yml; do \
		p="$(INVENTORY_DIR)/host_vars/$$host/$$f"; \
		printf '\n\033[1m== %s ==\033[0m\n' "$$p"; \
		if [ ! -f "$$p" ]; then echo "(missing)"; continue; fi; \
		if grep -q 'ANSIBLE_VAULT' "$$p"; then \
			ansible-vault view "$$p" 2>/dev/null \
				|| { printf '%s\n' "$(VAULT_PASSWORD_HINT)" >&2; exit 1; }; \
		else cat "$$p"; fi; \
	done

.PHONY: lint
lint: vault-init ## Playbook syntax check + ansible-lint
	ansible-playbook -i $(INVENTORY) --syntax-check playbooks/site.yml
	ansible-playbook -i $(INVENTORY) --syntax-check playbooks/tenant.yml
	ansible-playbook -i $(INVENTORY) --syntax-check playbooks/bootstrap.yml
	ansible-playbook -i $(INVENTORY) --syntax-check playbooks/backup.yml
	ansible-playbook -i $(INVENTORY) --syntax-check playbooks/restore.yml
	ansible-lint playbooks/site.yml playbooks/tenant.yml playbooks/bootstrap.yml playbooks/backup.yml playbooks/restore.yml

.PHONY: dry-run
dry-run: vault-init ## Dry-run (--check --diff); add TAGS=...
	ansible-playbook -i $(INVENTORY) $(PLAYBOOK) --check --diff $(if $(TAGS),--tags $(TAGS),)

.PHONY: deploy
deploy: vault-init ## One-shot: bootstrap the host, deploy the server, then apply the tenant state; TAGS=... runs only the server
	@echo "==> Bootstrapping the host (playbooks/bootstrap.yml: service account, Docker)..."
	ansible-playbook -i $(INVENTORY) playbooks/bootstrap.yml
	@echo "==> Deploying the NetBird server (playbooks/site.yml)..."
	ansible-playbook -i $(INVENTORY) $(PLAYBOOK) $(if $(TAGS),--tags $(TAGS),)
	@if [ -z "$(TAGS)" ]; then \
		echo "==> Applying the tenant config-as-code state (playbooks/tenant.yml)..."; \
		ansible-playbook -i $(INVENTORY) playbooks/tenant.yml -e tenant_commit=true; \
	fi

.PHONY: plan
plan: vault-init ## Tenant config-as-code: read-only diff (safe)
	ansible-playbook -i $(INVENTORY) playbooks/tenant.yml

.PHONY: apply
apply: vault-init ## Tenant config-as-code: apply desired state (strict via tenant_strict in host_vars)
	ansible-playbook -i $(INVENTORY) playbooks/tenant.yml -e tenant_commit=true

.PHONY: backup
backup: vault-init ## Back up the netbird_data volume (key stays in vault_managed.yml)
	ansible-playbook -i $(INVENTORY) playbooks/backup.yml

.PHONY: restore
restore: vault-init ## Restore FROM=backup/<host>/<stamp>
	@if [ -z "$(FROM)" ]; then echo "Usage: make restore FROM=backup/<host>/<timestamp>" >&2; exit 1; fi
	@restore_dir="$(abspath $(FROM))"; \
	if [ ! -d "$$restore_dir" ]; then echo "No such backup directory: $$restore_dir" >&2; exit 1; fi; \
	ansible-playbook -i $(INVENTORY) playbooks/restore.yml -e restore_from="$$restore_dir"

.PHONY: print
print: vault-init ## Print resolved host vars (incl. decrypted vault); HOST optional if single-host
	@host="$(HOST)"; \
	if [ -z "$$host" ]; then \
		host="$$(ansible-inventory -i $(INVENTORY) --list 2>/dev/null \
			| python3 -c 'import json,sys; h=list(json.load(sys.stdin).get("_meta",{}).get("hostvars",{})); print(h[0] if len(h)==1 else "")')"; \
	fi; \
	if [ -z "$$host" ]; then \
		echo "Usage: make print HOST=<hostname> (required when the inventory has no single host)" >&2; exit 1; \
	fi; \
	echo "Resolved host: $$host"; \
	ansible -i $(INVENTORY) "$$host" -m ansible.builtin.debug -a "var=hostvars[inventory_hostname]"
