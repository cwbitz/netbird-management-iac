# AGENTS.md

Ansible control node that deploys the **self-hosted NetBird server** (combined
`Management + Signal + Relay + STUN` container) with the dashboard and a built-in
Traefik reverse proxy onto a public Debian-family VPS. Idempotent and
version-controlled.

This project deploys the **server**; the NetBird **client agent** lives in the
sibling `docker-stack-iac` project. Tenant resources (users, groups, setup keys,
policies, networks, DNS) are managed against the running server's REST API via the
`community.ansible_netbird` collection; desired state lives in the per-host vars
and is rendered by `playbooks/tenant.yml` (config-as-code). **Peers are enrolled
devices, not codifiable state** — only their settings are managed; desired
enrollment is expressed through groups/setup keys/policies.

Managed hosts live in `inventory/hosts.yml` (local-only/gitignored; committed
template `inventory/hosts.yml.example`) and are never hardcoded into docs, roles,
or templates. The **node type is an inventory group** under the `netbird` umbrella,
so `hosts:` play patterns and `group_vars/<group>/` are the single source of truth:
`netbird_management` runs the self-hosted server stack (`roles/management`) and is
targeted by `playbooks/site.yml`, `tenant.yml`, `backup.yml`, `restore.yml`. The
`netbird` parent group spans every managed node, so cross-cutting playbooks
(`bootstrap.yml`, `host_keys.yml`, `ssh_agent_load.yml`) address all of them.
`make host-bootstrap` targets one host (`HOST=<name>`, default the single
management node). Entry playbooks: `playbooks/site.yml` (server deploy) and
`playbooks/tenant.yml` (tenant config-as-code).

## Integration contract (the mesh as a service)

This project owns the **mesh**: the management server, the tenant (groups,
networks, policies, DNS, setup keys) and the netbird agents of the hosts it
owns. Other projects consume the mesh **only through the running service's public
interface** — the management REST API and the embedded DNS — never by reading
this project's vars/vault. Rules:

- **Agent ownership = host ownership.** A host's netbird agent is owned by the
  project that owns the host (e.g. the central docker host's agent belongs to
  `docker-stack-iac`). A host is never split across projects; the mesh inputs it
  needs (`management URL` + a setup key) are credentials the operator supplies to
  that project's own vault.
- **Contract (the documented interface):** the tenant guarantees these groups,
  referenced by consumers by name:
  - `home-router` — routed-network gateways;
  - `observability` — the central monitoring stack host (scrapes `endpoint` and
    `home-router`; their peers push logs to it);
  - `endpoint` — observed-only clients with no routes (e.g. this server host).
  Setup keys assign them: `docker-host-enrollment` → [home-router, observability];
  `endpoint-enrollment` → [endpoint]; `admin-enrollment` → [admin].
- **Discovery inputs** for a consumer (held in the consumer's own vault): the
  management URL and a service-user PAT. Per-peer `ip` / `dns_label` / `groups`
  come straight from `GET /api/peers`; nothing needs to be exported from here.

## Secrets and local-only files

- `inventory/hosts.yml` — gitignored; holds each managed host's real name and
  connection address/port (`ansible_host` / `ansible_port`). The committed
  template `inventory/hosts.yml.example` carries the `CHANGE_ME_HOST_IP`
  placeholder, and the site preflight rejects it until it is replaced.
- `inventory/host_vars/<hostname>/vault.yml` — **gitignored, never committed**
  (even encrypted). The single per-host encrypted vault, holding everything:
  values the user supplies (the ACME email `vault_letsencrypt_email`, the SSH
  identities `vault_root_*`/`vault_ansible_*`/`vault_host_admin_*`, the optional
  first-owner credentials `vault_owner_*`), values the control node generates
  when the user leaves them empty and passes TO the host
  (`vault_datastore_encryption_key`, `vault_session_cookie_encryption_key`,
  `vault_relay_auth_secret`, `vault_owner_password`, `vault_host_ansible_password`,
  `vault_host_admin_password` (only when `host_admin_enabled` is set)), and the
  secrets the host returns (see below).
  Of the crypto keys, only `vault_datastore_encryption_key` is user-critical: it is
  **not** in the backup archive and a restore must reuse the same value, or the
  encrypted user data is unrecoverable. `vault_session_cookie_encryption_key` and
  `vault_relay_auth_secret` are auto-generated internals — leave them unedited
  (regenerating them only drops sessions / re-auths the relay; they must match
  across instances only for HA or an external relay, both out of scope here).
  Each identity may set a password and/or a private key file; SSH prefers the key,
  then the password. An optional public key file (`vault_*_ssh_pubkey_file`) is
  authorized for that account by `make host-bootstrap` when set. Because these are
  inputs, set them here to bring your own value (e.g. a datastore key on restore).
  Schema reference: `inventory/host_vars/example/vault.yml.example`.
  Secrets the host returns are stored here too (written by the role, never by
  hand): `vault_admin_service_user_access_token` (the `admin` service-user PAT,
  minted by NetBird during the first-owner bootstrap; expires, recreate it from
  the Dashboard) and `vault_setup_key_<name>` (one per new setup key; the API
  returns the secret only at creation, non-alphanumerics in the name replaced by
  `_`). Writes fill only missing values; existing non-empty values are preserved
  (never rotated).
- **After a host is reinstalled/reimaged** the host-returned values
  (`vault_admin_service_user_access_token` and the `vault_setup_key_<name>` keys)
  no longer exist on the new server. Because a present non-empty value is
  preserved, a stale token would survive and every tenant run would fail with
  "token rejected". Delete those keys from `vault.yml` (e.g. via `make vault-edit`)
  before the first deploy on the rebuilt host. With `vault_owner_email` set the
  first-owner bootstrap writes a fresh `vault_admin_service_user_access_token`;
  the tenant play writes the new `vault_setup_key_<name>` values. Without an
  email, set the PAT manually (see the Dashboard flow above).
- Vault password file: `~/.config/projects/netbird-iac/ansible_vault_password`
  (pointed to by `ansible.cfg`; auto-generated by `make vault-init`). An
  encrypted vault cannot be read without it.
- `backup/<host>/<stamp>/` — **gitignored**. Contains `netbird_data.tgz` (user
  PII, hashed credentials). It does **not** contain the encryption key; keep
  `vault.yml` (the datastore key) safe separately. Never commit
  backups; keep a copy off-host.
- `vault_admin_service_user_access_token` — the `admin` service-user PAT used by
  `playbooks/tenant.yml`. Provisioned automatically on a fresh deploy; otherwise
  set it manually in `vault.yml`. **It expires (max 365 days) and cannot be
  renewed** — when a tenant run reports it rejected, recreate one for the `admin`
  service user in the Dashboard (Team → Service Users) and update the vault. The
  project fails fast with these instructions instead of rotating proactively.

## Commands

- Control-node prerequisites: ansible-core within the supported range (pinned in
  `.tool-versions`, currently 2.19.x; asserted by the `playbooks/site.yml`
  preflight), Python 3, `openssl`, and the Galaxy collections from
  `requirements.yml`.
- `make install` — install the pinned toolchain (mise/asdf), the Galaxy
  collections, `sshpass`, and Keychain 3. sshpass is ensured by the internal
  `ensure-sshpass` target: passwordless `apt-get` when available, otherwise
  rootless into `~/.local/bin/sshpass`; a failure is fatal (install it manually
  and re-run). Only the `make host-bootstrap` password probe needs sshpass;
  steady-state Ansible password auth uses ssh_askpass, so the server/tenant/backup
  targets do not need it. Keychain is ensured by the internal `ensure-keychain`
  target: it downloads the pinned single-file zipapp (version + SHA256 in
  `keychain.pin`, Renovate-tracked) into `~/.cache/netbird-iac/` and installs it
  to `~/.local/bin/keychain`. It is a fallback ssh-agent used only when a
  configured private key has permissions OpenSSH rejects (e.g. WSL `/mnt/c`):
  every SSH-consuming target runs through the shared, project-agnostic
  `scripts/run-with-ssh-agent.sh` (driven by the `SSH_AGENT_*` environment
  variables), the internal `agent-fallback` prepares the agent (probe-gated by
  the internal `agent-needed`; `agent-ensure` is the unconditional variant) and
  loads the keys via `playbooks/ssh_agent_load.yml`, and the runner retries once
  on a refused-key failure. The `keychain-*` / `ensure-keychain` /
  `verify-keychain-pin` / `agent-*` targets are internal and are never exposed as
  public `make` commands.
- `make vault-init` — create the vault password file if missing (runs before
  every deploy/lint target).
- `make vault-view [HOST=<name>]` — print the decrypted `vault.yml`; **every host
  by default**, or a single host with HOST.
- `make vault-edit [HOST=<name>]` — edit one host's `vault.yml` (HOST, or the
  single host when the inventory holds exactly one; the target list is printed
  when it is omitted and the inventory has several); a plaintext `vault.yml` is
  encrypted first.
- `make host-init [HOST=<name>] [HOST_IP=<addr>] [HOST_PORT=<port>]` — scaffold
  `inventory/hosts.yml` and `inventory/host_vars/<name>/` **comment-free** from the
  committed `example/` template, encrypt the scaffolded `vault.yml`, and add the
  host to the inventory group (`GROUP`, default `netbird_management`) with its
  connection address/port (`HOST_IP` defaults to the `CHANGE_ME_HOST_IP`
  placeholder the site preflight rejects until replaced; `HOST_PORT` is omitted
  when unset). HOST defaults to `netbird-1`. Idempotent: existing files are kept,
  and an already-present host is left unchanged unless `FORCE_IP=1`, which
  overwrites a conflicting address/port. Edit the vault with
  `make vault-edit HOST=<name>`.
- `make host-bootstrap` — host init only: ensures Docker Engine + Compose v2
  (installing Docker CE when missing), sets APT/Docker mirrors for
  region-restricted hosts, and probes [ansible, admin, root] to create the
  `ansible` service account plus the `admin` account when `host_admin_enabled`
  is set. Run standalone
  to init a host without deploying; `make deploy` runs it automatically first
  (so a fresh/rebuilt host gets its service account before `site.yml` connects).
  The mirror parts are no-ops unless their vars are set.
- The internal `make lint` (`--syntax-check` + `ansible-lint`) is run by CI and
  hidden from `make help` (developers can still invoke it).
- `make dry-run` / `make deploy` — dry-run / deploy. `deploy` is the one-shot
  entry point: it runs `bootstrap.yml` (host init), then the server playbook,
  then applies the tenant state (`tenant.yml -e tenant_commit=true`); add
  `TAGS=...` to skip the tenant apply and run only the server. Tags:
  `netbird`, `netbird_preflight`, `netbird_config`, `netbird_deploy`,
  `netbird_owner`.
- `make plan` — tenant config-as-code, **read-only diff** (safe default).
- `make apply` — apply the tenant desired state. Requires
  `vault_admin_service_user_access_token`. Use it to change tenants without
  redeploying the server. Strict mode (also remove unmanaged resources) is off by
  default — absent, empty, or `false` `tenant_strict` means non-strict; only
  `tenant_strict: true` in `inventory/host_vars/<host>/main.yml` (or
  `-e tenant_strict=true`) enables it. The apply (and `deploy`'s tenant step) is
  retried on a transient network-level failure via `scripts/retry-transient.sh`,
  because the pinned collection does not retry its API calls; a configuration or
  token error still fails fast.
- `make backup` / `make restore FROM=backup/<host>/<stamp>` —
  stop-container snapshot of the `netbird_data` volume, and the paired restore.
  Keep `vault.yml` separately; a restore needs the same datastore key.
- `make monitoring` — optional host monitoring + host security (Debian-family):
  installs `prometheus-node-exporter`, `crowdsec` (journald-based detection) and
  the `crowdsec-firewall-bouncer` (nftables enforcement), and joins the host to
  the overlay through the shared `agent` role. Opt-in per host with
  `monitoring_enabled: true` in
  `host_vars/<host>/main.yml`; default off. node_exporter listens on
  `127.0.0.1:9100` plus the overlay address unless `node_exporter_listen_addr`
  is changed. The agent resolves its setup key (`peer_setup_key`) from the
  management node's vault (single source of truth; the route-less `endpoint` key by
  default, which grants no exit/LAN routes) and the exporters bind the overlay
  address; with `alloy_enabled: true`
  + `loki_url` an Alloy container ships journald SSH events to a central Loki
  over the overlay.
- `make print [HOST=<name>]` — resolved host vars incl. decrypted vault; HOST
  is auto-detected when the inventory has a single host.

## Important gotchas

- The public domain's A record must point at the host and **TCP 80/443 + UDP 3478**
  must be open **before** deploy, or Let's Encrypt (TLS-ALPN-01) and STUN will not
  work. The full contract is in `docs/components/networking.md`.
- The deploy **requires the non-root service account**: `playbooks/site.yml`
  asserts `host_ssh_user != root` (override with `host_allow_root_login=true`).
  `make host-bootstrap` probes [ansible, admin, root] and uses the first that
  works; when it is not `ansible` it creates `ansible`. Every explicitly set
  `vault_{root,ansible}_ssh_pubkey_file` / `vault_host_admin_ssh_pubkey_file` is
  authorized for the matching account (unset ignored, never generated); for
  `ansible` a missing key falls back to a password (`host_bootstrap_password`,
  else generated into `vault_host_ansible_password`), while key mode omits the
  password. The optional human `admin` account is created only when
  `host_admin_enabled` is set and always gets a password (generated into
  `vault_host_admin_password` when empty) plus any configured key. Passwords are
  hashed with a per-account random salt and applied with `update_password: on_create`,
  so re-runs are idempotent and a host-side password rotation is preserved.
  `ansible` gets passwordless sudo; `admin` gets password sudo (`ALL=(ALL) ALL`).
- The vault file must never stay plaintext: `write_vault` always encrypts, and a
  plaintext `vault.yml` (e.g. restored from backup) is re-encrypted on the next
  write by the vault helpers.
- Config files are rendered to `{{ stack_dir }}` and applied with
  `community.docker.docker_compose_v2`. **Rendering is the source of truth**; never
  edit the files on the target host (see `docs/components/roles.md`).
- `vault_admin_service_user_access_token` expires (max 365 days) and cannot be
  renewed — recreate it from the Dashboard when a tenant run reports it rejected
  (see Secrets above).

## Ansible conventions: probe & bootstrap host targeting

Shared by the `*-iac` repos; keep this chain statically resolvable so
`--syntax-check` stays clean:

- **Control-node-only plays** (preflight, the SSH probe, `host_keys`,
  `ssh_agent_load`) use `hosts: localhost` + `connection: local` — never
  `hosts: all` + `connection: local`.
- **The action play that follows a probe** targets a host/group that resolves
  from the static inventory. Never target a dynamic-only group: it forces either
  an empty-group declaration in the inventory or a `--syntax-check`
  "Could not match supplied host pattern" warning.
- **Single-host bootstrap** targets the probed host **by name**, with a safe
  default — `hosts: "{{ bootstrap_host | default(groups['<group>'] | default([]) | first | default('', true)) }}"` —
  and `make <target> HOST=<name>` passes `-e bootstrap_host=<name>`.
- **Multi-host bootstrap** targets the real inventory group. `add_host` only
  injects the probed identity/vars onto a host already present in the inventory;
  it never creates a play target.

## Scope

- **In scope**: self-hosted server + dashboard + built-in Traefik, embedded Dex
  IdP (local users), optional first-owner bootstrap (which also provisions the
  `admin` service-user PAT for tenant automation), tenant/ACL config-as-code
  (`playbooks/tenant.yml` + per-host vars), optional host monitoring/host
  security (`playbooks/monitoring.yml`), and backup/restore.
- **Not codifiable** (inherent): **peers** are enrolled devices (only settings are
  managed; devices re-enroll with setup keys), local-user **passwords** (returned
  once at creation), setup-key/PAT **secret values** (returned once), IdP client
  secrets (store in vault), and **audit/events** (read-only).
- **Out of scope (here)**: the client agent (owned by `docker-stack-iac`) and the
  NetBird Proxy / Agent Network quickstart components, plus external
  reverse-proxy modes beyond `trusted_peers`.

## Detailed documentation

- `docs/components/server.md` — combined server container (management + signal +
  relay + STUN), `config.yaml`, startup, first-owner bootstrap.
- `docs/components/dashboard.md` — the dashboard container.
- `docs/components/identity.md` — the embedded Dex IdP.
- `docs/components/traefik.md` — the built-in reverse proxy / TLS.
- `docs/components/networking.md` — network & port contract.
- `docs/components/data-and-volumes.md` — volumes, encryption keys, backup.
- `docs/components/tenant-config.md` — tenant config-as-code + collection gotchas.
- `docs/components/roles.md` — playbooks/roles layout, platform, image baseline.
- `docs/RUNBOOK.md` — operational procedures.
- `docs/IDP.md` — external identity providers.
