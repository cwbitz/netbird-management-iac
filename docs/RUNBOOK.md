# Runbook

Operational procedures for the self-hosted NetBird server. See `README.md` for
the overview, `docs/components/` for component design, and `AGENTS.md` for
contracts, conventions and gotchas.

## 0. Prerequisites (once)

- Public domain whose A record points at the host, with **TCP 80/443** and
  **UDP 3478** open — verify *before* the first deploy.
- Control node: ansible-core (pinned), Python 3, `openssl`, and the Galaxy
  collections: `make install`. It also installs `sshpass` (only the
  `host-bootstrap` password probe needs it) and the Keychain ssh-agent fallback.
- A host entry: `make host-init HOST=<hostname> HOST_IP=<address> [HOST_PORT=22]`
  — writes the connection address/port into `inventory/hosts.yml`, scaffolds
  `host_vars/<host>/` (comment-free) and encrypts a vault. Then set `domain_name`
  in `inventory/host_vars/<host>/main.yml` and the SSH creds / ACME email /
  optional owner in the vault (`make vault-edit HOST=<host>`). The connection
  address/port live in the inventory, not the vault.
- Create the non-root service account (as root, once): `make host-bootstrap`,
  then point the connection at it in `vault.yml`. Deploys refuse root unless
  `host_allow_root_login=true`.
- The vault password file is auto-created by the make targets
  (`~/.config/projects/netbird-iac/ansible_vault_password`); keep it safe.

## 1. Deploy

```bash
make dry-run     # dry run (--check --diff)
make deploy      # deploy the server, then apply the tenant state
                   # (TAGS=... keeps it server-only)
```

`make deploy` is the one-shot entry point: it runs `bootstrap.yml` (host init),
then the server deploy, then the tenant apply. It probes `ansible → admin → root`,
creates the `ansible` service account when needed, ensures Docker Engine + Compose
v2, generates missing secrets into the encrypted `vault.yml`, renders
`config.yaml` / `dashboard.env` / `docker-compose.yml` to `{{ stack_dir }}`
(`/opt/netbird`), starts the stack, waits for TLS, then optionally creates the
first owner. `make host-bootstrap` does the host init alone (no deploy). Exact
bootstrap rules (key vs. generated password, `host_admin_enabled`): `AGENTS.md`.

`make lint` (syntax check + `ansible-lint`) is an internal CI check; it is hidden
from `make help`, but developers can still run it locally.

Focused tags: `netbird`, `netbird_preflight`, `netbird_config`,
`netbird_deploy`, `netbird_owner` (`make deploy TAGS=<tag>`).

Verify:

```bash
ansible -i inventory/hosts.yml netbird -m ansible.builtin.ping
curl -fsS https://<domain>/oauth2/.well-known/openid-configuration >/dev/null && echo ok
ssh <host> 'cd /opt/netbird && docker compose ps'
```

**First deploy / GeoLite2**: the server blocks startup while downloading the
GeoLite2 DBs from `pkgs.netbird.io`. If the readiness wait times out, re-run
`make deploy` (the DBs persist), or pre-seed the DBs into the volume and set
`disable_geolite_update: true`.

## 2. First owner and access token

- With `vault_owner_email` set, the first owner is created automatically via
  `/api/setup` (works only while the instance has no accounts). The same run
  creates an `admin` service user and its PAT, stored as
  `vault_service_admin_access_token`.
- Without an email, open `https://<domain>/setup` and create the owner; then
  create an `admin` service user and an Access Token (Team → Service Users) and
  set `vault_service_admin_access_token` in `vault.yml`.
- PATs expire (max 365 days). When a tenant run reports the token rejected,
  recreate it in the Dashboard and update the vault.
- **Host reinstalled/reimaged**: the host-returned secrets in `vault.yml` are stale
  (they existed only on the old server). Move the file aside — or delete it — and
  redeploy: a missing file is regenerated (a fresh PAT via the first-owner
  bootstrap when `vault_owner_email` is set; new setup keys via `make apply`).
  Leaving a stale non-empty value there keeps the invalid token and every tenant
  run fails with "token rejected".

## 3. Day-2 changes (server)

- Edit `inventory/host_vars/<host>/main.yml` (non-secret) or the vault (secret),
  then `make deploy`. Config templates notify the restart handler, so the stack
  restarts when config changes.
- Image versions live in `roles/management/defaults/main.yml`
  (Renovate-tracked); the dashboard follows `latest`.
- Never edit rendered files under `{{ stack_dir }}` on the host — rendering is
  the source of truth.

## 4. Tenant configuration as code

```bash
make plan          # read-only diff (safe default)
make apply         # apply desired state
```

Desired state uses the `community.ansible_netbird` collection's native variables in
`inventory/host_vars/<host>/main.yml` (secret/PII in `vault.yml`). The play renders
a generated, gitignored directory (`.cache/tenant_config/<host>/`) and applies it.
Requires a valid `vault_service_admin_access_token`. `make deploy` already
applies the tenant state after the server deploy; use `apply` to change tenants
without touching the server, or `TAGS=...` to keep `deploy` server-only.

Strict mode (also remove unmanaged resources) is off by default; enable it per
host with `tenant_strict: true` in `inventory/host_vars/<host>/main.yml` (or
`-e tenant_strict=true`).

What you can codify:

| Resource | Codifiable? | Variable |
|---|---|---|
| Groups, Policies (ACL), Posture checks | Yes | `netbird_groups`, `netbird_policies`, `netbird_posture_checks` |
| Networks (routers/resources), DNS (nameservers/zones/settings) | Yes | `netbird_networks`, `netbird_dns_*` |
| Account settings (Dashboard settings) | Yes | `netbird_settings` |
| Services | Yes | `netbird_services`, `netbird_service_domains` |
| Users / service users | Yes* | `netbird_users`, `netbird_service_users`; embedded-IdP passwords are one-time |
| Setup keys | Yes* | `netbird_setup_keys`; expiry 1..31536000s (1 year max, never-expire not expressible); new secrets are persisted to `vault.yml` as `vault_<setup-key-name>` |
| Identity providers (external IdP) | No | Dashboard / `POST /api/identity-providers` (see `docs/IDP.md`) |
| Peers | No | enrolled devices: only settings are managed; devices re-enroll with setup keys |
| Audit / events | No | read-only |

`*` = the declaration is code, but a one-time secret is not reproducible; store it
in a secret manager. Unset options are skipped; `netbird_networks.routers` needs an
enrolled peer, and `netbird_services` / `netbird_service_domains` need a registered
proxy cluster.

Order for routed networks and exit nodes:

1. `make apply` — creates the `home-router` group, the setup key and the routed
   networks (bound by `routers[].peer_groups`, so no enrolled peer is needed yet),
2. enroll the client with that setup key — it auto-joins `home-router` and
   becomes the networks' routing peer automatically. No second `make apply` is
   needed for the networks to activate.

## 5. Host monitoring & security (optional)

```bash
make monitoring
```

Opt-in per host with `monitoring_enabled: true` in
`inventory/host_vars/<host>/main.yml` (default off). Installs
`prometheus-node-exporter` and `crowdsec` (journald-based detection) plus the
`crowdsec-firewall-bouncer` (nftables enforcement), and joins the host to the
overlay through the `agent` role so a central Prometheus/Alloy can reach it with
no public port. The agent uses the route-less `endpoint` setup key by default
(`peer_setup_key`, resolved from the management node's vault); node_exporter binds
`127.0.0.1:9100` plus the overlay address unless `node_exporter_listen_addr` is
changed.

```yaml
# inventory/host_vars/<host>/main.yml
monitoring_enabled: true
alloy_enabled: true                            # ship host logs to a central Loki
loki_url: "http://<loki-overlay-ip>:3100"
```

## 6. Mirrors for region-restricted hosts (optional)

`make host-bootstrap` (also run by `make deploy`) can point a host at alternative
package mirrors for hosts where the defaults are slow or blocked. It is a no-op
unless the variables are set, and touches nothing in the deploy baseline:

```yaml
# inventory/host_vars/<host>/main.yml
host_apt_mirror: "https://mirrors.tuna.tsinghua.edu.cn/debian"
docker_registry_mirrors:
  - "https://docker.1ms.run"
```

## 7. Backup and restore

```bash
make backup                              # -> backup/<host>/<stamp>/
make restore FROM=backup/<host>/<stamp>
```

- `backup` stops the container, archives the `netbird_data` volume
  (`netbird_data.tgz`), and restarts it. The archive holds user PII and hashed
  credentials.
- The encryption key is **not** in the archive. It is
  `inventory/host_vars/<host>/vault.yml` on the control node — **back it
  up separately and protect it**. Losing `vault_datastore_encryption_key` makes
  the archived data unrecoverable.
- `restore` replaces the data volume, then redeploys. `config.yaml` is
  re-rendered from the control node's current `vault.yml`, so that file
  must hold the **same** datastore key as when the data was archived.
- Only `vault_datastore_encryption_key` is restore-critical.
  `vault_session_cookie_encryption_key` and `vault_relay_auth_secret` are
  auto-generated internals and can be ignored (regenerating them only drops
  sessions / re-auths the relay).

Verify after restore: the OIDC discovery URL answers and users can log in.

## 8. Upgrade and rollback

- **Upgrade**: let Renovate bump the pinned tags (or edit
  `roles/management/defaults/main.yml`), then `make deploy`.
- **Version rollback**: set the previous tag and re-run `make deploy`.
- **Full rollback**: restore from a matching backup (data **and** the same
  `vault.yml`).
- **Config rollback**: `git revert` or edit the per-host vars, then `make
  deploy`.

## 9. Troubleshooting

| Symptom | Check / action |
|---|---|
| TLS / OIDC not answering | Domain A record resolves to the host; TCP 80/443 open; `docker logs netbird-traefik`. |
| STUN / relay clients fail | UDP 3478 open; Traefik owns `172.30.0.10`. |
| Readiness times out on first deploy | GeoLite2 download (§1); re-run or pre-seed the DBs. |
| Tenant run: token rejected | PAT expired — recreate it for the `admin` service user and update the vault (§2). |
| Host reinstalled / reimaged | `vault.yml` holds stale host-returned secrets — delete those keys before deploying so a fresh PAT/setup keys are written (§2). |
| A vault file is unreadable | It must be ansible-vault encrypted; the helpers re-encrypt a plaintext file on the next run. |
| SSH refuses the private key (`UNPROTECTED PRIVATE KEY FILE`, `are too open`) | The shared `scripts/run-with-ssh-agent.sh` starts the pinned Keychain agent, loads the vault keys and retries once automatically. If it still fails, check the `vault_*_ssh_privkey_file` paths and run `make agent-load`. |

Useful commands:

```bash
make print [HOST=<host>]                        # resolved vars incl. vault (HOST optional if single host)
ssh <host> 'cd /opt/netbird && docker compose logs -f netbird-server'
ssh <host> 'cd /opt/netbird && docker compose ps'
```

## 10. Secrets and safety

- Never commit `vault.yml` or `backup/` (all gitignored).
- The vault password file is required to decrypt any vault.
- Keep a copy of `vault.yml` (which holds the datastore key) off-host,
  separate from data backups.
