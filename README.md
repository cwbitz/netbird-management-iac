# netbird-iac

[English](README.md) | [简体中文](README.zh-CN.md)

Ansible IaC that idempotently deploys the **self-hosted NetBird server** onto a
public Debian-family VPS: the combined `Management + Signal + Relay + STUN`
container, the NetBird dashboard, and a built-in Traefik reverse proxy that
issues Let's Encrypt certificates automatically.

## What it deploys

```
┌───────────────────────────── public VPS ──────────────────────────────┐
│  TCP 80/443                        UDP 3478                           │
│     │                                   │                             │
│  netbird-traefik ───────────────────────┼ netbird-server              │
│  (Let's Encrypt, TLS-ALPN)              │ (Management + Signal +      │
│     │                                   │  Relay + STUN + Dex)        │
│  netbird-dashboard                   (STUN)                           │
└───────────────────────────────────────────────────────────────────────┘
```

- **Embedded Dex IdP** (NetBird ≥ 0.62): local users out of the box, no external
  IdP required. External OIDC providers can be added later from the Dashboard.
- **Pinned server image** (Renovate-tracked); the dashboard only ships moving
  tags upstream, so it follows `latest`.

## Requirements

- A Linux VM with at least 1 CPU / 2 GB RAM, publicly reachable on **TCP 80 and
  443** and **UDP 3478**.
- A **public domain** whose A record points at the VM.
- Docker Engine + the Compose v2 plugin. Installed automatically via Docker's
  official install script (`https://get.docker.com`) when missing (Debian-family);
  set `install_docker: false` to require a preinstalled Docker instead.
- On the control node: `mise` or `asdf`, `openssl`, and SSH access to the host.
  `sshpass` is only needed for the `make host-bootstrap` password probe and is
  auto-installed by `make install`; `make install` also installs the pinned
  Keychain 3 (an optional ssh-agent fallback for private keys whose permissions
  OpenSSH rejects, e.g. under WSL).

## Quickstart

```bash
# 1. Toolchain + collections
make install

# 2. Create a host from the committed template (vault.yml is encrypted for you)
make host-init HOST=netbird-1
#    - edit inventory/hosts.yml                       (hostname)
#    - edit inventory/host_vars/netbird-1/main.yml    (domain, ACME email)
#    - edit the encrypted vault:
make vault-edit HOST=netbird-1
#      (IP, SSH creds, owner)

# 3. Dry-run, deploy (deploy also applies the tenant state)
make dry-run
make deploy
```

`make lint` (syntax check + `ansible-lint`) is an internal check run by CI; it is
hidden from `make help` but developers can still run it locally.

`make deploy` is the one-shot entry point: it bootstraps the host, deploys the
server, then applies the tenant state. On a fresh/rebuilt host the `ansible`
service account does not exist yet, so `deploy` runs the same host bootstrap as
`make host-bootstrap` first (probes `ansible → admin → root`, creates the
account, ensures Docker). To do host init without deploying, run
`make host-bootstrap` on its own.

Deploys run as a **non-root service account** (`playbooks/site.yml` refuses root
unless `host_allow_root_login=true`). Bootstrap creates it; point the connection
at it in `vault.yml`:

```bash
#   vault_ansible_user: ansible
#   vault_ansible_ssh_privkey_file: ~/.ssh/...   (or vault_ansible_password)
```

`make host-bootstrap` probes `ansible → admin → root` and uses the first that
works; when it is not `ansible` it creates the account. It also ensures Docker
Engine + Compose v2 (installing Docker CE when missing) and applies the mirrors
below. Each configured `vault_<id>_ssh_pubkey_file` is authorized for its account
(`ansible`, `admin` or `root`); unset is ignored. For `ansible`, no public key
means a password is set instead (generated into the encrypted vault). When the
`admin` identity is configured, its account is created/updated too. Private key
paths are set in `vault_<id>_ssh_privkey_file` (paths only, never raw keys).

With `owner_email` set, the first owner is created automatically via `/api/setup`
(if `owner_password` is empty, one is generated into `vault.yml`). The
same run creates an `admin` service user and a PAT for it, stored as
`vault_admin_service_user_access_token` for the tenant phase, then deletes the
one-time owner token. With no email, onboard at `https://<domain>/setup` — that
page works only while the instance has no accounts.

Tags: `netbird`, `netbird_preflight`, `netbird_config`, `netbird_deploy`,
`netbird_owner`. Use `make deploy TAGS=netbird_config`.

## Identity providers (IdP)

Local users are the default, backed by the **embedded Dex** IdP the server ships
(NetBird ≥ 0.62); the dashboard manages them directly. External **OIDC** providers
— Google, Microsoft Entra, Okta, Keycloak, Zitadel, **Authentik**, Pocket ID or a
generic OIDC provider — can run alongside local users. Add them in
**Settings → Identity Providers** (or via `POST /api/identity-providers`); this
is runtime tenant config, not part of the server-deploy role.

### Using an existing self-hosted Authentik

Register a **confidential OAuth2/OpenID** provider in Authentik, put the NetBird
redirect URL in it, then add a *Generic OIDC* IdP in NetBird with issuer
`https://authentik.example.com/application/o/netbird/`. For a **remote-access**
deployment:

- Both the user's browser **and** the NetBird server must reach the issuer
  (discovery, JWKS, token, and the login/consent pages) over valid public TLS.
- If Authentik is behind an IP allowlist limited to LAN/CGNAT sources, public
  browsers and the server are rejected; expose the OIDC/login paths or allowlist
  the required source IPs.
- JWT group sync: Authentik's `profile` scope includes `groups`; enable *JWT
  group sync* in NetBird and use the `groups` claim. (Zitadel exposes *roles* and
  needs an Action to flatten them.)

## Managing tenants/ACLs with Ansible (config-as-code)

The `community.ansible_netbird` collection manages **tenant resources** against
the running server's REST API. Desired state lives in the per-host Ansible
variables (`inventory/host_vars/<host>/main.yml` for non-secret values,
`vault.yml` for secrets/PII) using the collection's native variable names; the
play renders them into a generated, gitignored directory
(`.ansible_cache/tenant_config/<host>/`) and applies them declaratively, with
plain names resolved to IDs and resources applied in dependency order.

```bash
make plan          # read-only diff (safe default)
make apply         # apply the desired state
```

`make deploy` already applies the tenant state after the server deploy; use the
`apply` target to change tenants without touching the server, or `TAGS=...` to
keep `deploy` server-only. Strict mode (also remove unmanaged resources) is off
by default — an absent, empty, or `false` `tenant_strict` in
`inventory/host_vars/<host>/main.yml` means non-strict; only `tenant_strict:
true` (or `-e tenant_strict=true`) enables it.

Requires `vault_admin_service_user_access_token` (provisioned automatically on a
fresh deploy; otherwise create an `admin` service user + token under
Team → Service Users). What you can and cannot codify:

| Resource | Codifiable? | Variable |
|---|---|---|
| Groups, Policies (ACL), Posture checks | Yes | `netbird_groups`, `netbird_policies`, `netbird_posture_checks` |
| Networks (routers/resources), DNS (nameservers/zones/settings) | Yes | `netbird_networks`, `netbird_dns_*` |
| Account settings (Dashboard settings) | Yes | `netbird_settings` |
| Services | Yes | `netbird_services`, `netbird_service_domains` |
| Users / service users | Yes* | `netbird_users`, `netbird_service_users`; embedded-IdP passwords are one-time |
| Setup keys | Yes* | `netbird_setup_keys`; expiry 1..31536000s (1 year max, never-expire not expressible); newly created secrets are persisted to `vault_managed.yml` as `vault_setup_key_<name>` |
| Identity providers (external IdP) | Yes* | client secret must be stored in vault |
| **Peers** | **No** | enrolled devices: only settings are managed; devices re-enroll with setup keys |
| Audit / events | No | read-only |

`*` = the *declaration* is code, but a one-time secret is not reproducible; store
it in a secret manager.

Some options need infrastructure beyond the server (unset ones are skipped):
- `netbird_networks.routers` needs an enrolled peer; `netbird_services` /
  `netbird_service_domains` need a registered proxy cluster.

## Backup & restore

```bash
make backup                              # -> backup/<host>/<stamp>/
make restore FROM=backup/<host>/<stamp>  # paired restore
```

The backup stops the container for a consistent SQLite copy and archives the
`netbird_data` volume to `backup/<host>/<stamp>/`. The encryption key is **not**
in the archive: it lives in the control node's
`inventory/host_vars/<host>/vault.yml`, which you must back up separately.
Restore re-renders `config.yaml` from that file, so it must hold the
**same** datastore key as when the data was archived, or the data cannot be
decrypted. `backup/` is gitignored; keep a copy off-host.

## Mirrors for region-restricted hosts (optional)

`make host-bootstrap` (also run by `make deploy`) can point a host at
alternative package mirrors — useful for China-based VPS. It is a no-op unless
the variables are set, and touches nothing in the deploy baseline:

```yaml
# inventory/host_vars/<host>/main.yml
host_apt_mirror: "https://mirrors.tuna.tsinghua.edu.cn/debian"
docker_registry_mirrors:
  - "https://docker.1ms.run"
```

## Layout

```
inventory/           # hosts.yml(.example), group_vars/netbird, host_vars/example
playbooks/site.yml   # server preflight + netbird_server role
playbooks/tenant.yml # tenant config-as-code (community.ansible_netbird)
roles/netbird_server # defaults (image pins), tasks, templates/
roles/helpers/       # shared vault-secret provisioning
docs/RUNBOOK.md      # operations runbook (deploy, backup/restore, rollback)
```

## Secrets

Never commit vaults. Ownership is split by direction:
`inventory/host_vars/<host>/vault.yml` is control-authoritative — user-supplied
values plus control-generated inputs passed to the host (the datastore/session/
relay keys, the owner/ansible passwords). `vault_managed.yml` is
host-authoritative — secrets the host returns (the `admin` PAT, setup-key
secrets). A key lives in exactly one file. **Back up `vault.yml`** — losing
`vault_datastore_encryption_key` makes encrypted user data unrecoverable.

## License

See `LICENSE`.
