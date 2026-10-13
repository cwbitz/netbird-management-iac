# AGENTS.md

Ansible control node that deploys the **self-hosted NetBird server** (combined
`Management + Signal + Relay + STUN` container) with the dashboard and a built-in
Traefik reverse proxy onto a public Debian-family VPS. Idempotent and
version-controlled.

This project deploys the **server**; the NetBird **client agent** lives in the
sibling `docker-stack-iac` project. Tenant resources (users, groups, setup keys,
policies, networks, DNS) are managed against the running server's REST API via
the `community.ansible_netbird` collection; desired state lives in the per-host
vars and is rendered by `playbooks/tenant.yml` (config-as-code). **Peers are
enrolled devices, not codifiable state** — only their settings are managed;
desired enrollment is expressed through groups/setup keys/policies.

Managed mesh nodes live in `inventory/hosts.yml` (local-only/gitignored;
committed template `inventory/hosts.yml.example`) and are never hardcoded into
docs, roles, or templates. **Node type is an inventory group** under the
`netbird` umbrella, so `hosts:` play patterns and `group_vars/<group>/` are the
single source of truth:

- `netbird_management` — runs the server stack (`roles/management`); targeted by
  `playbooks/site.yml`, `tenant.yml`, `backup.yml`, `restore.yml`.
- `netbird_agent` — runs only the NetBird agent (`roles/agent`): both routing
  nodes (a routed-network gateway / exit node) and plain endpoints live here;
  they run the same role and differ only by `netbird_agent_routing`.

The `netbird` parent group spans every managed node, so cross-cutting playbooks
(`bootstrap.yml`, `host_keys.yml`, `ssh_agent_load.yml`) address all of them.
`make host-bootstrap` targets one host (`HOST=<name>`, default the single
management node). Entry playbooks: `playbooks/site.yml` (server deploy),
`playbooks/tenant.yml` (tenant config-as-code) and `playbooks/agent.yml`
(`make agent`, the agent-only nodes).

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

**Supported platform**: Debian-family Linux with Docker Engine + Compose v2. When
Docker is missing the preflight installs Docker CE via Docker's official install
script (`https://get.docker.com`; disable with `install_docker: false`, which then
fails with install guidance). Non-Debian support is best-effort; automatic install
is Debian-only.

## Secrets and local-only files

- `inventory/host_vars/<hostname>/vault.yml` — **gitignored, never committed**
  (even encrypted). The single per-host encrypted vault, holding everything:
  values the user supplies (topology `vault_host.{ip,port}`, the public domain
  `vault_domain_name`, the ACME email `vault_letsencrypt_email`, the SSH
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
- `make vault-edit HOST=<name>` — edit one host's `vault.yml` (HOST required; the
  target list is printed when it is omitted); a plaintext `vault.yml` is
  encrypted first.
- `make host-init HOST=<name>` — scaffold `inventory/hosts.yml` and
  `inventory/host_vars/<name>/` from the committed `example/` template, and
  encrypt the scaffolded `vault.yml` (edit it with `make vault-edit HOST=<name>`).
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

- The public domain's A record must point at the host and TCP 80/443 plus UDP
  3478 must be open **before** deploy, or Let's Encrypt (TLS-ALPN) and STUN will
  not work.
- `server.store.encryptionKey` in `config.yaml` **must keep base64 padding** (Go
  `base64.StdEncoding`); `server.authSecret` (relay) has its padding stripped.
  Losing the datastore key makes encrypted user data unrecoverable.
- `/api/setup` is unauthenticated and only works while the instance has **no
  accounts**. The owner-bootstrap tasks are skipped on later runs. On first setup
  the role also bootstraps the tenant credential: it requests a short-lived owner
  access token (`create_pat`, 7 days), creates an `admin` service user and a PAT
  for it, persists it as `vault_admin_service_user_access_token`, then deletes the
  owner token. The owner token is never written to disk or logged. With
  `vault_owner_email` set and no owner password, a password is generated into
  `vault.yml` (read it there; an existing non-empty value is preserved);
  without an email the provided password is never applied and logs a warning
  (onboard at `/setup` instead).
- The startup readiness check hits
  `https://<domain>/oauth2/.well-known/openid-configuration`, which drives the
  first certificate issuance.
- The dashboard image only publishes moving tags (`latest` / `sha-*` / `pr-*`),
  so `dashboard_version` cannot be pinned; the server image is pinned and tracked
  by Renovate.
- **GeoLite2 at startup**: the server downloads MaxMind GeoLite2 DBs from
  `pkgs.netbird.io` on first start and **blocks startup until they finish**;
  `server.disableGeoliteUpdate` only disables updates, not the initial load. On
  hosts where that CDN is slow, the readiness check times out (the container keeps
  downloading and the DBs persist, so a later re-run succeeds). For such hosts,
  pre-seed `GeoLite2-City_*.mmdb` + `geonames_*.db` into the volume (the geonames
  file needs a real `geonames` table) and set `disable_geolite_update: true`.
- A bind-mounted config change does **not** recreate the container, so the
  `config.yaml` / `dashboard.env` template tasks notify the `[NetBird] Restart the
  stack` handler.
- The deploy **requires the non-root service account**: `playbooks/site.yml`
  asserts `host_ssh_user != root` (override with `host_allow_root_login=true`).
  `make host-bootstrap` probes [ansible, admin, root] and uses the first that
  works; when it is not `ansible` it creates `ansible`. Every explicitly set
  `vault_{root,ansible}_ssh_pubkey_file` / `vault_host_admin_ssh_pubkey_file` is
  authorized for the matching account (unset ignored, never generated); for
  `ansible` a missing key falls back
  to a password (`host_bootstrap_password`, else generated into
  `vault_host_ansible_password`), while key mode omits the password. The optional human
  `admin` account is created only when `host_admin_enabled` is set and always gets
  a password (generated into `vault_host_admin_password` when empty) plus any configured
  key. Passwords are hashed with a per-account random salt and applied with
  `update_password: on_create`, so re-runs are idempotent and a host-side password
  rotation is preserved. `ansible` gets passwordless sudo; `admin` gets password
  sudo (`ALL=(ALL) ALL`).
- The vault file must never stay plaintext: `write_vault` always encrypts, and a
  plaintext `vault.yml` (e.g. restored from backup) is re-encrypted on the next
  write by the vault helpers.
- The built-in Traefik owns `172.30.0.10` in the `netbird` bridge network and is
  the only address management trusts as a reverse proxy
  (`reverseProxy.trustedHTTPProxies`).
- The data volume uses an explicit name (`netbird_data`), stable regardless of the
  compose project directory.
- Config files are rendered to `{{ stack_dir }}` (`/opt/netbird` by default, in
  `inventory/group_vars/netbird_management/main.yml`) and applied with
  `community.docker.docker_compose_v2`. Rendering is the source of truth; never
  edit the files on the target host.
- `netbird_networks.routers` needs an enrolled peer, and `netbird_services` /
  `netbird_service_domains` need a registered reverse-proxy cluster, which only
  the self-hosted proxy software itself can create (BYOP); the collection can only
  delete one. Unset options are skipped.
- Setup keys: the collection preflight requires `expires_in > 0` (max 31536000),
  so a **never-expiring** key (`expires_in: 0`) cannot be declared in
  `netbird_setup_keys`; create one once out-of-band. Newly created key secrets are
  persisted as `vault_setup_key_<name>`.
- Routed networks bind their gateway by peer **group** (`routers[].peer_groups`,
  e.g. `home-router`), not by an individual peer name. The group is created by the
  tenant play and the client's setup key auto-assigns it, so a network is applied
  on the **first** run (no chicken-and-egg); the client becomes its routing peer
  automatically when it enrolls. No enrollment readiness gate is needed. An
  individual peer name (`routers[].peer`) is still supported when a single
  gateway must be pinned, but then the peer must already be enrolled.
- Exit nodes: a `0.0.0.0/0` (and `::/0`) network resource routed via a peer IS the
  exit node. It needs (a) `masquerade: true` on the router, (b) an accept policy
  from the using group to the routing peer's group (declare an explicit one — the
  built-in `Default` rule is removed by strict), and (c) IP forwarding on the
  routing peer. **Auto Apply** (v0.55.0+, default on) is a Dashboard/client
  setting the API/collection cannot express.
- Edition boundaries (self-hosted): core (groups, policies, posture checks, DNS,
  networks, setup keys, users, settings) is open source; SCIM/IdP provisioning,
  audit/SIEM streaming, MDM/EDR, HA and MSP/multi-tenant require an Enterprise
  license. Agent Network is a separate self-hosted deployment (not the management
  container) and is not managed here.

## Role layout

- `playbooks/site.yml` — server preflight + the `management` role.
- `playbooks/bootstrap.yml` — **optional, opt-in** host tuning: APT mirror
  (`host_apt_mirror`, security mirror derived) + Docker registry mirrors
  (`docker_registry_mirrors`), ensures Docker Engine + Compose v2 (installing
  Docker CE when missing), probes the SSH identities and creates the
  least-privilege `ansible` service account when not already connected as it, plus
  the `admin` account when `host_admin_enabled` is set (authorizes each identity's
  `vault_*_ssh_pubkey_file` when set; otherwise a password, and the admin always
  gets one) + NOPASSWD sudo for `ansible` and password sudo for `admin`. Never
  runs as part of `site.yml`. Debian-family only for APT.
- `playbooks/backup.yml` / `playbooks/restore.yml` — stop-container backup of the
  `netbird_data` volume, and the paired restore (which needs the same datastore
  key in `vault.yml`).
- `playbooks/tenant.yml` — tenant config-as-code on `localhost` against the server
  API using `vault_admin_service_user_access_token`. The collection's `configure`
  role reads raw YAML (no templating), so the play renders the per-host variables
  into a generated, gitignored directory (`.cache/tenant_config/<host>/`)
  and passes it as `config_dir`; `commit`/`strict` come from
  `tenant_commit`/`tenant_strict` (both default false = preview). Users/service
  users use the separate `netbird_user` module and are applied afterward from
  `netbird_users` / `netbird_service_users`, gated on commit (their `auto_groups`
  take plain group names, resolved to IDs first).
- Tenant desired state — Ansible variables in the per-host vars: non-secret in
  `host_vars/<host>/main.yml`, secret/PII in `vault.yml`, using the collection's
  native names (`netbird_settings`, `netbird_groups`, `netbird_posture_checks`,
  `netbird_policies`, `netbird_dns_nameserver_groups`, `netbird_dns_zones`,
  `netbird_dns_disabled_management_groups`, `netbird_networks`,
  `netbird_setup_keys`, `netbird_services` + `netbird_service_domains`, and
  `netbird_users` / `netbird_service_users`). Plain names are resolved to IDs.
  The generated directory is never hand-edited. Exception: within
  `netbird_settings` the peer expiry durations use the project convention
  `peer_login_expire_seconds` / `peer_inactivity_expire_seconds`, which
  `playbooks/tenant.yml` maps to the collection's `peer_login_expiration` /
  `peer_inactivity_expiration` fields when rendering; the `*_expiration_enabled`
  toggles keep the collection names.
- `roles/helpers/` — a real role (no `tasks/main.yml`), always invoked via
  `include_role` + `tasks_from`:
  - `control_node_prereqs.yml` — openssl availability check.
  - `install_docker.yml` — install Docker Engine + Compose v2 when missing
    (`install_docker`, default true; false makes a missing Docker fatal).
  - `read_vault.yml` / `write_vault.yml` — read/encrypt the per-host vault file.
  - `dispatch_secrets.yml` / `generate_secrets.yml` /
    `store_secret.yml` — per-host encrypted secret provisioning.
- `roles/management/` — the deploy. `tasks/main.yml` runs preflight checks,
  provisions secrets, renders `config.yaml` / `dashboard.env` /
  `docker-compose.yml` from `templates/`, deploys with `docker_compose_v2`, waits
  for TLS readiness, then optionally creates the first owner.
  `defaults/main.yml` holds every image tag behind a `_version` var.
- `roles/agent/` — joins an agent-only node to the overlay (the NetBird agent
  container, in `agent_dir` = `/opt/netbird-agent`). Used by
  `playbooks/agent.yml` (`make agent`, the `netbird_agent` group) and by
  `roles/monitoring`. `peer_setup_key` (resolved from the management node's vault)
  decides the peer's group; `netbird_agent_routing: true` enables IP forwarding
  for a routed-network gateway / exit node.
- `roles/monitoring/` — optional, opt-in (`make monitoring`). Apt-installs
  `prometheus-node-exporter` + `crowdsec` + `crowdsec-firewall-bouncer` on a
  Debian-family host and includes the `agent` role; skipped unless
  `monitoring_enabled: true`. The play sets `gather_facts: false` and the role
  gathers facts itself, so non-opted hosts are never contacted.

## Image version baseline

Every tag is rendered only through role-default vars, each carrying a
`# renovate: datasource=docker depName=<image>` annotation so Renovate keeps it
current (see `renovate.json`).

| Component | Registry | Version var |
|---|---|---|
| netbird-server | dockerhub | `server_version` |
| netbird-dashboard | dockerhub | `dashboard_version` (upstream has no pinned tags) |
| traefik | dockerhub | `traefik_version` |
| netbird-agent | ghcr.io | `netbird_agent_version` |
| alloy | dockerhub | `alloy_version` |

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
- **Out of scope (here)**: the client agent (`docker-stack-iac`) and optional
  quickstart components (NetBird Proxy, CrowdSec, external reverse-proxy modes).
