# ==============================================================================
# NetBird self-hosted IaC - Makefile wrapper
# ==============================================================================
# Entry points around ansible-playbook / ansible-lint. Run `make help` for the
# target list. Override HOST=... (single host), TAGS=... (focused run).

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Fixed paths (not operator knobs): the playbooks and inventory are part of the
# repo layout. Non-mainstream cases can call ansible directly.
ANS_PLAY      := ansible-playbook
PLAYBOOK      := playbooks/site.yml
INVENTORY     := inventory/hosts.yml
INV           := $(INVENTORY)
INVENTORY_DIR := inventory

# Command-line inputs (set at invocation, e.g. `make restore FROM=<dir>`).
TAGS ?=
HOST ?=
FROM ?=
# Refresh SSH host keys before connecting (HOST_KEY=1). Useful after a managed
# host is rebuilt: its new host key would otherwise fail the "host key changed"
# check. hostkey-init scans every inventory host and (re)writes its key into the
# control node's known_hosts; deploy/dry-run/host-bootstrap call it when set.
HOST_KEY ?=
KNOWN_HOSTS ?= $(HOME)/.ssh/known_hosts

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
SSHPASS_BIN   ?= $(HOME)/.local/bin/sshpass

# Keychain 3 (pinned single-file zipapp) is an OPTIONAL fallback ssh-agent: it is
# only started when OpenSSH refuses a private key whose permissions cannot be
# fixed (e.g. the WSL /mnt/c mount, mode 0777). It is ensured by the internal
# `ensure-keychain` target (invoked by `install`); all `keychain-*` targets are
# internal and never exposed as public make commands. The download URL is fixed;
# a failure aborts so the operator can place the asset manually and re-run.
KEYCHAIN_PIN     := $(CURDIR)/keychain.pin
KEYCHAIN_VERSION := $(shell awk '!/^#/ && NF {print $$1; exit}' $(KEYCHAIN_PIN))
KEYCHAIN_SHA256  := $(shell awk '!/^#/ && NF {print $$2; exit}' $(KEYCHAIN_PIN) | sed 's/^sha256://')
KEYCHAIN_URL     ?= https://github.com/danielrobbins/keychain/releases/download/$(KEYCHAIN_VERSION)/keychain-$(KEYCHAIN_VERSION).pyz
KEYCHAIN_BIN     ?= $(HOME)/.local/bin/keychain
KEYCHAIN_CACHE   ?= $(HOME)/.cache/netbird-iac
KEYCHAIN_ASSET   := $(KEYCHAIN_CACHE)/keychain-$(KEYCHAIN_VERSION).pyz
# Start (or reuse) the Keychain agent in the CURRENT shell; --eval prints the
# SSH_AUTH_SOCK / SSH_AGENT_PID exports on stdout (banner goes to stderr).
KEYCHAIN_AGENT   := eval "$$($(KEYCHAIN_BIN) agent start --eval --quiet 2>/dev/null)"

# ------------------------------------------------ shared ssh-agent runner ----
# Identical across the 5 IaC projects: the generic scripts/run-with-ssh-agent.sh
# is driven by the SSH_AGENT_* environment variables, so only the per-project
# values below differ (the private-key hostvar names, and the inventory/playbook
# paths already defined above). The agent is prepared proactively only when a
# configured key has permissions OpenSSH would refuse (e.g. WSL /mnt/c), and the
# runner retries once on a refused-key failure as a safety net.
SSH_AGENT_ENV   ?= $(HOME)/.cache/iac/ssh-agent.env
SSH_AGENT_RUN   ?= $(CURDIR)/scripts/run-with-ssh-agent.sh
# Per-project fork: hostvars holding the control-node private-key paths.
SSH_AGENT_KEY_VARS ?= vault_host_ansible_ssh_privkey_file vault_host_admin_ssh_privkey_file vault_host_root_ssh_privkey_file
export SSH_AGENT_ENV
export SSH_AGENT_KEYCHAIN_BIN  := $(KEYCHAIN_BIN)
export SSH_AGENT_ANS_PLAY      := $(ANS_PLAY)
export SSH_AGENT_INVENTORY     := $(INV)
export SSH_AGENT_LOAD_PLAYBOOK := playbooks/ssh_agent_load.yml

# (shared) Probe: exit 0 when a configured private key has unsafe permissions
# (group/other bits set, e.g. 0777), i.e. OpenSSH would refuse it.
SSH_AGENT_PROBE := ansible-inventory -i $(INV) --list 2>/dev/null | SSH_AGENT_KEY_VARS="$(SSH_AGENT_KEY_VARS)" python3 -c "import json,os,sys; names=os.environ['SSH_AGENT_KEY_VARS'].split(); vs=json.load(sys.stdin).get('_meta',{}).get('hostvars',{}); ks={os.path.expanduser(h.get(v)) for h in vs.values() for v in names if h.get(v)}; sys.exit(0 if any(os.path.isfile(k) and (os.stat(k).st_mode & 0o077) for k in ks) else 1)"

# (shared) Canned recipe: prepare the Keychain ssh-agent. Reuse a loaded agent;
# otherwise start Keychain and load the configured keys. SSH_AGENT_FORCE=1 skips
# the permission probe. Writes SSH_AGENT_ENV for the runner to source.
define SSH_AGENT_PREPARE
	@set -e; \
	mkdir -p "$$(dirname "$(SSH_AGENT_ENV)")"; \
	rm -f "$(SSH_AGENT_ENV)"; \
	if [ -n "$${SSH_AUTH_SOCK:-}" ] && ssh-add -l >/dev/null 2>&1; then \
		echo "ssh-agent: reusing loaded agent"; \
		echo "export SSH_AUTH_SOCK='$$SSH_AUTH_SOCK'" > "$(SSH_AGENT_ENV)"; exit 0; \
	fi; \
	if [ "$(SSH_AGENT_FORCE)" != "1" ] && ! $(SSH_AGENT_PROBE); then \
		echo "ssh-agent: not needed (keys usable or password auth)"; exit 0; \
	fi; \
	echo "ssh-agent: starting Keychain and loading keys"; \
	eval "$$($(KEYCHAIN_BIN) agent start --eval --quiet 2>/dev/null)"; \
	echo "export SSH_AUTH_SOCK='$$SSH_AUTH_SOCK'" > "$(SSH_AGENT_ENV)"; \
	$(ANS_PLAY) -i $(INV) $(SSH_AGENT_LOAD_PLAYBOOK)
endef

# (internal) Diagnostic probe: exit 0 when a configured private key would be
# refused by OpenSSH. Shared across the 5 projects.
agent-needed: vault-init
	@$(SSH_AGENT_PROBE)

# (internal) Prepare the Keychain ssh-agent, probe-gated (Ansible targets).
agent-fallback: ensure-keychain
	$(SSH_AGENT_PREPARE)

# (internal) Prepare the Keychain ssh-agent unconditionally. Unused by this
# Ansible-only project, kept so the block is identical across the 5 projects.
agent-ensure: ensure-keychain
	$(SSH_AGENT_PREPARE)
agent-ensure: SSH_AGENT_FORCE := 1

# (internal) Load the connection keys into the Keychain ssh-agent
agent-load: vault-init ensure-keychain
	@$(KEYCHAIN_AGENT); \
	$(ANS_PLAY) -i $(INV) $(SSH_AGENT_LOAD_PLAYBOOK)

# (internal) Ensure the Keychain agent has identities loaded
agent-check: ensure-keychain
	@$(KEYCHAIN_AGENT); \
	if ssh-add -l >/dev/null 2>&1; then \
		echo "ssh-agent: identities loaded"; \
	else \
		echo "ERROR: the Keychain ssh-agent has no identities loaded."; \
		echo "Load the connection keys with: make agent-load"; \
		exit 1; \
	fi

.PHONY: help
help: ## Show this help
	@printf '\nUsage: make <target> [VAR=value ...]\n\n'
	@awk 'BEGIN {FS = ":.*?## "} \
		/^[a-zA-Z0-9_-]+:.*?## / { if ($$1 == "help") { hd = $$2; next } \
			printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2 } \
		END { printf "  \033[36m%-25s\033[0m %s\n", "help", hd }' \
		$(MAKEFILE_LIST)
	@printf '\n'

.PHONY: install
install: ensure-sshpass ensure-keychain ## Install the pinned toolchain, collections, and control-node dependencies
	@if command -v mise >/dev/null 2>&1; then mise install; \
	elif command -v asdf >/dev/null 2>&1; then asdf install; \
	else echo "Neither mise nor asdf found; install one, or ensure ansible-core 2.19.x is on PATH." >&2; exit 1; fi
	@$(MAKE) --no-print-directory ensure-ansible-collections

# Internal. Install/refresh the pinned Ansible collections into the
# project-local `collections/` dir (selected by ansible.cfg's `collections_path`,
# which REPLACES the global ~/.ansible/collections). ansible-galaxy is
# idempotent and version-aware: it no-ops when the pinned versions are present,
# and installs/upgrades to the exact requirements.yml pins otherwise. The
# requirements.yml GitHub-tarball entry (community.ansible_netbird) installs the
# same way as Galaxy-hosted collections.
ensure-ansible-collections:
	@ansible-galaxy collection install -r requirements.yml

# Internal helpers (not listed in `make help`; not part of the public interface).
.PHONY: ensure-ansible-collections ensure-sshpass ensure-keychain keychain-fetch verify-keychain-pin \
        agent-needed agent-fallback agent-ensure agent-load agent-check
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

# (internal) download the pinned Keychain asset into the fixed cache path.
keychain-fetch:
	@set -e; \
	mkdir -p "$(KEYCHAIN_CACHE)"; \
	if [ -f "$(KEYCHAIN_ASSET)" ] \
	   && printf '%s  %s\n' "$(KEYCHAIN_SHA256)" "$(KEYCHAIN_ASSET)" | sha256sum -c - >/dev/null 2>&1; then \
		exit 0; \
	fi; \
	echo "downloading keychain v$(KEYCHAIN_VERSION)..."; \
	if ! curl -fsSL -o "$(KEYCHAIN_ASSET).tmp" "$(KEYCHAIN_URL)"; then \
		echo "ERROR: failed to download Keychain v$(KEYCHAIN_VERSION)." >&2; \
		echo "  URL: $(KEYCHAIN_URL)" >&2; \
		echo "  Download it manually to: $(KEYCHAIN_ASSET)" >&2; \
		echo "  then re-run 'make install'." >&2; \
		rm -f "$(KEYCHAIN_ASSET).tmp"; \
		exit 1; \
	fi; \
	mv "$(KEYCHAIN_ASSET).tmp" "$(KEYCHAIN_ASSET)"

# (internal) verify the cached asset against keychain.pin (used by CI).
verify-keychain-pin: keychain-fetch
	@set -e; \
	printf '%s  %s\n' "$(KEYCHAIN_SHA256)" "$(KEYCHAIN_ASSET)" | sha256sum -c -; \
	echo "keychain pin OK: v$(KEYCHAIN_VERSION)"

# (internal) ensure the pinned asset is installed (and unmodified) in ~/.local/bin.
ensure-keychain: verify-keychain-pin
	@set -e; \
	if [ -f "$(KEYCHAIN_BIN)" ] \
	   && printf '%s  %s\n' "$(KEYCHAIN_SHA256)" "$(KEYCHAIN_BIN)" | sha256sum -c - >/dev/null 2>&1; then \
		echo "keychain:  present (v$(KEYCHAIN_VERSION), $(KEYCHAIN_BIN))"; exit 0; \
	fi; \
	mkdir -p "$$(dirname "$(KEYCHAIN_BIN)")"; \
	install -m 0755 "$(KEYCHAIN_ASSET)" "$(KEYCHAIN_BIN)"; \
	echo "keychain installed: $(KEYCHAIN_BIN) (v$(KEYCHAIN_VERSION))"

.PHONY: host-init
host-init: vault-init ## Scaffold host_vars/<HOST> from the example
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
host-bootstrap: vault-init agent-fallback ## Create the ansible service account (bootstrap.yml); HOST_KEY=1 refreshes host keys first
	@if [ -n "$(HOST_KEY)" ]; then $(MAKE) --no-print-directory hostkey-init; fi; \
	$(SSH_AGENT_RUN) $(ANS_PLAY) -i $(INVENTORY) playbooks/bootstrap.yml

# (internal) Scan every inventory host and (re)write its SSH host key into the
# control node's known_hosts (removing any stale entry first). Invoked by
# deploy/dry-run/host-bootstrap when HOST_KEY=1, and usable standalone.
.PHONY: hostkey-init
hostkey-init: vault-init
	@set -e; \
	nh="$(KNOWN_HOSTS)"; mkdir -p "$$(dirname "$$nh")"; tmp=$$(mktemp); \
	$(ANS_PLAY) -i $(INVENTORY) playbooks/host_keys.yml -e host_keys_out="$$tmp" >/dev/null; \
	mapfile -t lines < <(python3 -c "import json; [print(f\"{t['name']}\t{t['host']}\t{t['port']}\") for t in json.load(open('$$tmp'))]"); \
	rm -f "$$tmp"; \
	if [ "$${#lines[@]}" -eq 0 ]; then echo "ERROR: no hosts resolved from the inventory."; exit 1; fi; \
	for line in "$${lines[@]}"; do \
		name=$$(printf '%s' "$$line" | cut -f1); host=$$(printf '%s' "$$line" | cut -f2); port=$$(printf '%s' "$$line" | cut -f3); \
		echo "host key: $$name ($$host:$$port)"; \
		ssh-keygen -R "$$host" -f "$$nh" >/dev/null 2>&1 || true; \
		if [ "$$port" != "22" ]; then ssh-keygen -R "[$$host]:$$port" -f "$$nh" >/dev/null 2>&1 || true; fi; \
		ssh-keyscan -T 5 -p "$$port" -t rsa,ecdsa,ed25519 "$$host" >> "$$nh" 2>/dev/null || { echo "ERROR: ssh-keyscan failed for $$host:$$port"; exit 1; }; \
	done; \
	echo "host keys refreshed in $$nh"

.PHONY: vault-init
vault-init: ## One-time: generate the vault password (idempotent)
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
vault-edit: vault-init ## Edit a per-host vault (plaintext auto-encrypted first)
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
vault-view: vault-init ## View a per-host vault (read-only)
	@host="$(HOST)"; \
	if [ -z "$$host" ]; then \
		host="$$(ansible-inventory -i $(INVENTORY) --list 2>/dev/null \
			| python3 -c 'import json,sys; h=list(json.load(sys.stdin).get("_meta",{}).get("hostvars",{})); print(h[0] if len(h)==1 else "")')"; \
	fi; \
	if [ -z "$$host" ]; then \
		echo "Usage: make vault-view HOST=<hostname> (required when the inventory has no single host)" >&2; exit 1; \
	fi; \
	for f in vault.yml; do \
		p="$(INVENTORY_DIR)/host_vars/$$host/$$f"; \
		printf '\n\033[1m== %s ==\033[0m\n' "$$p"; \
		if [ ! -f "$$p" ]; then echo "(missing)"; continue; fi; \
		if grep -q 'ANSIBLE_VAULT' "$$p"; then \
			ansible-vault view "$$p" 2>/dev/null \
				|| { printf '%s\n' "$(VAULT_PASSWORD_HINT)" >&2; exit 1; }; \
		else cat "$$p"; fi; \
	done

.PHONY: lint
# (internal) Syntax check + ansible-lint (invoked by CI).
lint: vault-init
	$(ANS_PLAY) --syntax-check playbooks/site.yml
	$(ANS_PLAY) --syntax-check playbooks/tenant.yml
	$(ANS_PLAY) --syntax-check playbooks/bootstrap.yml
	$(ANS_PLAY) --syntax-check playbooks/backup.yml
	$(ANS_PLAY) --syntax-check playbooks/restore.yml
	$(ANS_PLAY) --syntax-check playbooks/monitoring.yml
	ansible-lint playbooks/site.yml playbooks/tenant.yml playbooks/bootstrap.yml playbooks/backup.yml playbooks/restore.yml playbooks/monitoring.yml

# Transient-network retry for the tenant apply. The pinned collection does not
# retry API calls, and a cross-region link can drop a small fraction of TLS
# handshakes; scripts/retry-transient.sh re-runs only on a network-level failure
# (a config/auth error still fails fast). See the script for the knobs.
RETRY_RUN          ?= $(CURDIR)/scripts/retry-transient.sh
TENANT_RETRY_MAX   ?= 5
TENANT_RETRY_DELAY ?= 8

.PHONY: dry-run
dry-run: vault-init agent-fallback ## Dry-run (--check --diff); HOST_KEY=1 refreshes host keys first
	@if [ -n "$(HOST_KEY)" ]; then $(MAKE) --no-print-directory hostkey-init; fi; \
	$(SSH_AGENT_RUN) $(ANS_PLAY) -i $(INVENTORY) $(PLAYBOOK) --check --diff $(if $(TAGS),--tags $(TAGS),)

.PHONY: deploy
deploy: vault-init agent-fallback ## One-shot: bootstrap the host, deploy the server, then apply the tenant state; TAGS=... runs only the server; HOST_KEY=1 refreshes host keys first
	@if [ -n "$(HOST_KEY)" ]; then $(MAKE) --no-print-directory hostkey-init; fi
	@echo "==> Bootstrapping the host (playbooks/bootstrap.yml: service account, Docker)..."
	$(SSH_AGENT_RUN) $(ANS_PLAY) -i $(INVENTORY) playbooks/bootstrap.yml
	@echo "==> Deploying the NetBird server (playbooks/site.yml)..."
	$(SSH_AGENT_RUN) $(ANS_PLAY) -i $(INVENTORY) $(PLAYBOOK) $(if $(TAGS),--tags $(TAGS),)
	@if [ -z "$(TAGS)" ]; then \
		echo "==> Applying the tenant config-as-code state (playbooks/tenant.yml)..."; \
		RETRY_MAX=$(TENANT_RETRY_MAX) RETRY_DELAY=$(TENANT_RETRY_DELAY) \
			$(RETRY_RUN) $(SSH_AGENT_RUN) $(ANS_PLAY) -i $(INVENTORY) playbooks/tenant.yml -e tenant_commit=true; \
	fi

.PHONY: plan
plan: vault-init agent-fallback ## Tenant config-as-code: read-only diff (safe)
	$(SSH_AGENT_RUN) $(ANS_PLAY) -i $(INVENTORY) playbooks/tenant.yml

.PHONY: apply
apply: vault-init agent-fallback ## Tenant config-as-code: apply desired state (strict via tenant_strict in host_vars)
	RETRY_MAX=$(TENANT_RETRY_MAX) RETRY_DELAY=$(TENANT_RETRY_DELAY) \
		$(RETRY_RUN) $(SSH_AGENT_RUN) $(ANS_PLAY) -i $(INVENTORY) playbooks/tenant.yml -e tenant_commit=true

.PHONY: monitoring
monitoring: vault-init agent-fallback ## Optional host monitoring + host security (CrowdSec + node_exporter); opt-in via monitoring_enabled
	$(SSH_AGENT_RUN) $(ANS_PLAY) -i $(INVENTORY) playbooks/monitoring.yml

.PHONY: backup
backup: vault-init agent-fallback ## Back up the netbird_data volume (key stays in vault.yml)
	$(SSH_AGENT_RUN) $(ANS_PLAY) -i $(INVENTORY) playbooks/backup.yml

.PHONY: restore
restore: vault-init agent-fallback ## Restore FROM=backup/<host>/<stamp>
	@if [ -z "$(FROM)" ]; then echo "Usage: make restore FROM=backup/<host>/<timestamp>" >&2; exit 1; fi
	@restore_dir="$(abspath $(FROM))"; \
	if [ ! -d "$$restore_dir" ]; then echo "No such backup directory: $$restore_dir" >&2; exit 1; fi; \
	$(SSH_AGENT_RUN) $(ANS_PLAY) -i $(INVENTORY) playbooks/restore.yml -e restore_from="$$restore_dir"

.PHONY: print
print: vault-init ## Print resolved host vars (incl. decrypted vault)
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
