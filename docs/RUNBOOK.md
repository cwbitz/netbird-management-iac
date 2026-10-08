# Runbook

[English](RUNBOOK.md) | [简体中文](RUNBOOK.zh-CN.md)

Operational procedures for the self-hosted NetBird server. See `README.md` for
the overview and `AGENTS.md` for design notes and gotchas.

## 0. Prerequisites (once)

- Public domain whose A record points at the host, with **TCP 80/443** and
  **UDP 3478** open — verify *before* the first deploy.
- Control node: ansible-core (pinned), Python 3, `openssl`, and the Galaxy
  collections: `make install`.
- A host entry: `make host-init HOST=<hostname>` (scaffolds and encrypts
  `vault.yml`), then edit `inventory/hosts.yml`,
  `inventory/host_vars/<host>/main.yml` (domain, ACME email) and the vault
  (`make vault-edit HOST=<host>`) for IP, SSH creds and owner.
- Create the non-root service account (as root, once): `make host-bootstrap`,
  then point the connection at it in `vault.yml`. Deploys refuse root unless
  `host_allow_root_login=true`.
- The vault password file is auto-created by the make targets
  (`~/.config/projects/netbird-iac/ansible_vault_password`); keep it safe.
- `sshpass` is needed only by the `make host-bootstrap` password probe;
  `make install` auto-installs it (passwordless `apt-get`, else rootless
  into `~/.local/bin`).

## 1. Deploy

```bash
make dry-run     # dry run (--check --diff)
make deploy      # deploy the server, then apply the tenant state
                   # (TAGS=... keeps it server-only)
```

`make lint` (syntax check + `ansible-lint`) is an internal CI check; it is hidden
from `make help`, but developers can still run it locally.

Focused tags: `netbird`, `netbird_preflight`, `netbird_config`,
`netbird_deploy`, `netbird_owner` (`make deploy TAGS=<tag>`).

The deploy asserts inputs and the non-root account, generates missing secrets
into the encrypted `vault.yml` (user, control-generated and host-returned
secrets all live there), renders
`config.yaml` / `dashboard.env` /
`docker-compose.yml` to `{{ stack_dir }}` (`/opt/netbird`), starts the stack,
waits for TLS, then optionally creates the first owner.

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
  `vault_admin_service_user_access_token`.
- Without an email, open `https://<domain>/setup` and create the owner; then
  create an `admin` service user and an Access Token (Team → Service Users) and
  set `vault_admin_service_user_access_token` in `vault.yml`.
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
- Image versions live in `roles/netbird_server/defaults/main.yml`
  (Renovate-tracked); the dashboard follows `latest`.
- Never edit rendered files under `{{ stack_dir }}` on the host — rendering is
  the source of truth.

## 4. Tenant configuration as code

```bash
make plan          # read-only diff (safe default)
make apply         # apply desired state
```

Strict mode (also remove unmanaged resources) is off by default; enable it per
host with `tenant_strict: true` in `inventory/host_vars/<host>/main.yml` (or
`-e tenant_strict=true`).

Desired state uses the collection's native variables in
`inventory/host_vars/<host>/main.yml` (secret/PII in `vault.yml`). The play
renders a generated, gitignored directory
(`.cache/tenant_config/<host>/`) and applies it. Requires a valid
`vault_admin_service_user_access_token`.

Order for routed networks and exit nodes:

1. `make apply` — creates the `home-router` group, the setup key and the routed
   networks (bound by `routers[].peer_groups`, so no enrolled peer is needed yet),
2. enroll the client with that setup key — it auto-joins `home-router` and
   becomes the networks' routing peer automatically. No second `make apply` is
   needed for the networks to activate.

## 5. Backup and restore

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

## 6. Upgrade and rollback

- **Upgrade**: let Renovate bump the pinned tags (or edit
  `roles/netbird_server/defaults/main.yml`), then `make deploy`.
- **Version rollback**: set the previous tag and re-run `make deploy`.
- **Full rollback**: restore from a matching backup (data **and** the same
  `vault.yml`).
- **Config rollback**: `git revert` or edit the per-host vars, then `make
  deploy`.

## 7. Troubleshooting

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

## 8. Secrets and safety

- Never commit `vault.yml` or `backup/` (all gitignored).
- The vault password file is required to decrypt any vault.
- Keep a copy of `vault.yml` (which holds the datastore key) off-host,
  separate from data backups.
