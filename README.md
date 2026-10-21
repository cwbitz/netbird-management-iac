<div align="center">

# NetBird IaC

Ansible IaC that idempotently deploys the **self-hosted NetBird server** onto a
public Debian-family VPS: the combined `Management + Signal + Relay + STUN`
container, the NetBird dashboard, and a built-in Traefik reverse proxy that
issues Let's Encrypt certificates automatically.

Self-hosted NetBird, deployed as code

[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)
</div>

- **Embedded Dex IdP** — local users out of the box, no external IdP required.
- **Pinned server image** (Renovate-tracked); the dashboard only ships moving tags
  upstream, so it follows `latest`.
- **Tenant as code** — groups, policies, networks, DNS, setup keys, users and more
  applied to the server's REST API via `make plan` / `make apply`.

Procedures live in [`docs/RUNBOOK.md`](docs/RUNBOOK.md); component design in
[`docs/components/`](docs/components/) and project conventions, contracts and
gotchas in [`AGENTS.md`](AGENTS.md).

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

## Requirements

- A Linux VM with at least 1 CPU / 2 GB RAM, publicly reachable on **TCP 80 and
  443** and **UDP 3478**, with a **public domain** whose A record points at it.
- Docker Engine + the Compose v2 plugin — installed automatically via Docker's
  official install script when missing (Debian-family); set `install_docker:
  false` to require a preinstalled Docker instead.
- On the control node: `mise` (or `asdf`), Python 3, `openssl`, and SSH access.
  `make install` installs the pinned toolchain and collections, `sshpass` (only
  the `host-bootstrap` password probe needs it) and the Keychain ssh-agent
  fallback.

## Quickstart

```bash
# 1. Toolchain + collections
make install

# 2. Scaffold the host from the committed template: writes the inventory entry
#    (address/port) and an encrypted vault.yml, and creates host_vars/.
make host-init HOST=netbird-1 HOST_IP=203.0.113.10 HOST_PORT=22
#    - inventory/host_vars/netbird-1/main.yml  -> domain_name
#    - the encrypted vault (make vault-edit HOST=netbird-1)
#      -> SSH creds, ACME email, optional owner

# 3. Dry-run, then deploy (deploy also applies the tenant state)
make dry-run
make deploy
```

`make deploy` is the one-shot entry point: it bootstraps the host, deploys the
server, then applies the tenant state (`TAGS=...` keeps it server-only);
`make host-bootstrap` does the host init on its own. Deploys run as a non-root
service account. Connections, secrets and the first-owner bootstrap are covered
in the [runbook](docs/RUNBOOK.md).

## Node type

The host runs the self-hosted server stack; its inventory group
`management` is the single source of truth for `hosts:` play patterns and
`group_vars/<group>/`. The project-owned baseline for every managed host (engine
range) lives in the committed `inventory/group_vars/all/main.yml`, so `hosts.yml`
carries topology only. `make host-bootstrap HOST=<name>` targets one host,
defaulting to the single management node.

## Features

| Feature | Enable | Procedure |
|---|---|---|
| Tenant config-as-code (groups, policies, networks, DNS, setup keys, users, ...) | per-host vars | [Runbook §4](docs/RUNBOOK.md) |
| Host monitoring & security (node_exporter, CrowdSec, Alloy) | `monitoring_enabled: true` | [Runbook §5](docs/RUNBOOK.md) |
| Host firewall (default-deny inbound; mesh contract 80/443/tcp, 3478/udp) | `firewall_enabled: true` | [Runbook §5b](docs/RUNBOOK.md) |
| SSH hardening (key-only admin; root policy via `sshd_permit_root_login`) | `sshd_hardening_enabled: true` | [Runbook §5b](docs/RUNBOOK.md) |
| Region-restricted APT / Docker mirrors | `apt_mirror`, `docker_registry_mirrors` | [Runbook §6](docs/RUNBOOK.md) |
| Backup & restore | — | [Runbook §7](docs/RUNBOOK.md) |
| External identity providers (OIDC) | Dashboard / API | [`docs/IDP.md`](docs/IDP.md) |

## Layout

```
inventory/           # hosts.yml(.example), group_vars/{all}, host_vars/example
playbooks/site.yml   # server preflight + management role
playbooks/tenant.yml # tenant config-as-code (community.ansible_netbird)
roles/management     # defaults (image pins), tasks, templates/
roles/agent          # NetBird agent container (overlay join for monitoring)
roles/monitoring     # optional host security + exporters (+ the agent role)
roles/firewall       # optional base firewall (nftables; the mesh port contract)
roles/sshd           # optional key-only SSH (sshd drop-in)
roles/helpers/       # shared vault-secret provisioning
docs/RUNBOOK.md      # operations runbook (deploy, backup/restore, rollback)
docs/IDP.md          # external identity providers (runtime, not managed here)
```

## Secrets

Never commit vaults. The single per-host encrypted vault
`inventory/host_vars/<host>/vault.yml` holds user-supplied values, control-
generated inputs passed to the host (the datastore/session/relay keys, the
owner/iac passwords), and secrets the host returns (the `admin` PAT,
setup-key secrets). Only `vault_datastore_encryption_key` is user-critical:
**back up `vault.yml`** and reuse the same value on restore, or encrypted user
data is unrecoverable. See [Runbook §10](docs/RUNBOOK.md).

## License

See `LICENSE`.
