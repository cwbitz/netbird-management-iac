# Runbook

Operational procedures for the self-hosted NetBird server. See `README.md` for
the overview, `docs/components/` for component design, and `AGENTS.md` for
contracts, conventions and gotchas.

## 0. Prerequisites (once)

- Public domain whose A record points at the host, with **TCP 80/443** and
  **UDP 3478** open — verify *before* the first deploy.
- Control node: ansible-core (pinned), Python 3, `openssl`, and the Galaxy
  collections: `make install`. It also installs `sshpass` (only the
  `deploy` password probe needs it) and the Keychain ssh-agent fallback.
- A host entry: `make prep HOST=<hostname> IP=<address> [PORT=22]`
  — writes the connection address/port into `inventory/hosts.yml`, scaffolds
  `host_vars/<host>/` (comment-free) and encrypts a vault. Then set
  `server.domain_name` and `server.acme_email` in
  `inventory/host_vars/<host>/main.yml` and the SSH creds / optional owner in
  the vault (`make edit HOST=<host>`). The connection address/port live
  in the inventory, not the vault.
- Create the non-root service account (as root, once): `make deploy`,
  then point the connection at it in `vault.yml`. Deploys refuse root unless
  `allow_root_login=true`.
- Host security is opt-in per host and safe to add later: enable the base
  firewall (the mesh contract stays open) and key-only SSH hardening only after
  `make deploy` has authorized the `iac` key — see §5b.
- The vault password file is auto-created by the make targets
  (`~/.config/projects/netbird-management-iac/ansible_vault_password`); keep it safe.

## 1. Deploy

```bash
make dry-run     # dry run (--check --diff)
make deploy      # deploy the server, apply the tenant state, then monitoring
                   # (TAGS=... keeps it server-only)
```

`make deploy` is the one-shot entry point: it runs `bootstrap.yml` (host init),
then the server deploy, then the tenant apply, then `monitoring.yml` (host
monitoring plus the overlay agent). The server deploy waits for the process to
log its HTTP listener (`server.server_ready_retries`, default 120 attempts) before it
checks the public TLS endpoint (`server.tls_wait_retries`, default 24) — a fresh volume
downloads the geolocation databases first, which can take several minutes on a
slow link. It probes `iac → admin → root`, creates the `iac` automation account when needed, ensures Docker Engine + Compose
v2, generates missing secrets into the encrypted `vault.yml`, renders
`config.yaml` / `dashboard.env` / `docker-compose.yml` to `{{ stack_dir }}`
(`/opt/netbird`), starts the stack, waits for TLS, then optionally creates the
first owner. The host init (`playbooks/bootstrap.yml`) runs first inside every
`make deploy`. Exact bootstrap rules (key vs. generated password,
`create_admin_account`): `AGENTS.md`.

`make lint` (syntax check + `ansible-lint`) is an internal CI check; it is hidden
from `make help`, but developers can still run it locally.

Focused tags: `netbird`, `netbird_preflight`, `netbird_config`,
`netbird_deploy`, `netbird_owner` (`make deploy TAGS=<tag>`), plus the opt-in host
security roles `firewall` and `sshd`.

Verify:

```bash
ansible -i inventory/hosts.yml netbird -m ansible.builtin.ping
curl -fsS https://<domain>/oauth2/.well-known/openid-configuration >/dev/null && echo ok
ssh <host> 'cd /opt/netbird && docker compose ps'
```

**First deploy / GeoLite2**: the server blocks startup while downloading the
GeoLite2 DBs from `pkgs.netbird.io`. If the readiness wait times out, re-run
`make deploy` (the DBs persist), or pre-seed the DBs into the volume and set
`server.disable_geolite_update: true`.

## 2. First owner and access token

- With an entry for the owner in `netbird_users` (`role: owner`, the single
  definition of the owner identity), the first owner is created automatically via
  `/api/setup` (works only while the instance has no accounts). The same run
  creates an `admin` service user and its PAT, stored as
  `vault_service_admin_access_token`.
- Without such an entry, open `https://<domain>/setup` and create the owner; then
  create an `admin` service user and an Access Token (Team → Service Users) and
  set `vault_service_admin_access_token` in `vault.yml`.
- PATs expire (max 365 days). When a tenant run reports the token rejected,
  recreate it in the Dashboard and update the vault.
- **Host reinstalled/reimaged**: `make deploy REBUILD=1` prunes the declared
  host-returned secrets from the target host's `vault.yml` automatically — the
  `admin` service-user PAT plus one `vault_<setup-key-name>` per
  `netbird_setup_keys` entry — after backing the vault up under
  `backup/vaults/<host>/`. It prints the removed key names, never a value.
  - Only `deploy` prunes; `dry-run` never touches the vault.
  - The prune assumes a fresh server; if the server's data volume survived the
    reinstall, restore the token from the backup under `backup/vaults/<host>/`.
  - A multi-host inventory requires `HOST=<name>` for the prune.
  - Keep everything else: deleting the whole vault would lose
    `vault_datastore_encryption_key` (a reinstall needs the same value), the SSH
    account passwords, `vault_owner_password` and the CrowdSec
    machine/bouncer credentials.
  - With an owner entry in `netbird_users`, the first-owner bootstrap writes a
    fresh PAT; the tenant play creates the new setup keys. Without an owner
    entry, set the PAT manually (see above). If the prune was skipped, delete
    the stale keys with `make edit` before the first run.

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
`inventory/host_vars/<host>/.config/netbird/tenant.yml` (secret/PII in
`vault.yml`); the committed template is
`inventory/host_vars/example/.config/netbird/tenant.yml.example`, and
`make print HOST=<host>` prints the file along with the resolved host vars. The
play renders a generated, gitignored directory (`.cache/tenant_config/<host>/`) and applies it.
Before rendering, the play validates the effective state locally
(`scripts/validate_tenant_config.py`) and fails with a per-field report on an
unusable value. Requires a valid `vault_service_admin_access_token`. `make deploy`
already applies the tenant state after the server deploy; use `apply` to change
tenants without touching the server, or `TAGS=...` to keep `deploy` server-only.

Strict mode (also remove unmanaged resources) is off by default; enable it per
host with `tenant_strict: true` in `inventory/host_vars/<host>/.config/netbird/tenant.yml`
(or `-e tenant_strict=true`).

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

Opt-in per host by enabling a component under `monitoring:` in
`inventory/host_vars/<host>/main.yml` (default off). Installs
`prometheus-node-exporter` and `crowdsec` (journald-based detection) plus the
`crowdsec-firewall-bouncer` (nftables enforcement), and joins the host to the
overlay through the `agent` role so a central Prometheus/Alloy can reach it with
no public port. The agent uses the route-less `rhost_setup_key` (group
`rhost`) by default (`netbird_peer_setup_key`, resolved from the host's own
vault); node_exporter
binds the overlay address only (no local or public listener), and a boot drop-in
waits for the overlay so the bind survives a reboot.

```yaml
# inventory/host_vars/<host>/main.yml
monitoring:
  node_exporter:
    enabled: true
  alloy:
    enabled: true                              # ship host logs to a central Loki
    loki_push_url: "http://<central-peer>.netbird.selfhosted:3100"   # or "<overlay-ip>:3100"
```

When `monitoring.alloy.enabled` is set and the central Loki does not answer from
the host (the peer has not enrolled yet after a rebuild, for example), the run
prints a warning and still deploys the Alloy stack; it starts shipping as soon
as the central peer is reachable.

With `monitoring.alloy.prometheus_remote_write_url` set, Alloy also scrapes the
local exporters every `monitoring.alloy.scrape_interval` (default `15s`,
accepted range 1s-30s) and pushes the samples to the central Prometheus
remote-write receiver, tagged `source="agent"`. The cadence has to stay inside
the dashboards' 60s `rate()` window: at 60s each `rate()` query sees a single
sample and every panel built on one renders "No data".

The toggles converge **off** as well as on: setting `node_exporter.enabled: false`,
`crowdsec.enabled: false` or `alloy.enabled: false` stops and disables the
matching units (node_exporter; crowdsec + crowdsec-firewall-bouncer) and removes
the Alloy containers (the compose project in `/opt/monitoring`) on the next run.
Packages, the compose file and the rendered configuration are kept, so
re-enabling needs no reinstall. With every component disabled the playbook
includes only the cleanup tasks, and a unit that does not exist on the host is
left alone instead of failing.

node_exporter has no listen-address knob: it binds the host's **overlay address
only** — there is no local or public listener, and the central Prometheus scrapes
it over the mesh. A systemd drop-in
(`/etc/systemd/system/prometheus-node-exporter.service.d/10-overlay-wait.conf`)
makes that bind survive a reboot: the overlay address is created by the agent
container *after* systemd has started the unit, so the drop-in waits for the
address and retries instead of failing with `cannot assign requested address`.

## 5b. Host firewall & SSH hardening (optional)

Both are off by default and enabled per host in
`inventory/host_vars/<host>/main.yml`; both run inside `site.yml` (so `make
deploy` keeps them converged) and have their own tag:

```bash
make deploy TAGS=firewall   # default-deny inbound (roles/firewall)
make deploy TAGS=sshd       # key-only SSH (roles/sshd)
```

```yaml
# inventory/host_vars/<host>/main.yml
firewall:
  enabled: true
sshd:
  hardening_enabled: true        # only after `deploy` keyed `iac`
```

- **Firewall**: enforces the mesh contract (TCP 80/443, UDP 3478 —
  [`components/networking.md`](components/networking.md)) plus SSH and the
  overlay; everything else is reachable over the overlay only. The port matrix
  is not configurable: it follows `server.exposed_port` / `server.stun_port` and is
  re-verified from the control node after applying (skipped while the stack is
  not running). Details:
  [`components/firewall.md`](components/firewall.md).
- **SSH hardening**: closes password login (plus the PAM keyboard-interactive and
  empty-password paths) and applies `sshd.permit_root_login` (default `no`). It
  proves a key-only login as the chosen identity (`iac`, or root when allowed)
  first and rolls itself back on any failed verification. The human `admin`
  account keeps its password for the **console** only — set
  `host_admin_ssh_pubkey_file` (in the host's main.yml) to keep SSH for it.
  Details:
  [`components/sshd-hardening.md`](components/sshd-hardening.md).
- Rollback (or console recovery):
  `ssh <host> 'systemctl disable --now firewall && nft delete table inet basefw'`
  for the firewall;
  `rm /etc/ssh/sshd_config.d/00-sshd-hardening.conf && systemctl reload ssh`
  for SSH — then disable the matching knob so a later deploy does not re-apply it.

## 6. Mirrors for region-restricted hosts (optional)

`make deploy` can point a host at alternative package mirrors for hosts where
the defaults are slow or blocked. It is a no-op
unless the variables are set, and touches nothing in the deploy baseline. The
Debian security suite derives from the single base mirror (a `…/debian` path
maps to its `…/debian-security` sibling), so there is no separate security knob:

```yaml
# inventory/host_vars/<host>/main.yml
apt_mirror: "https://mirrors.tuna.tsinghua.edu.cn/debian"
docker_registry_mirrors:
  - "https://docker.1ms.run"
```

## 7. Upgrade and rollback

- **Upgrade**: let Renovate bump the pinned tags (or edit
  `roles/management/defaults/main.yml`), then `make deploy`.
- **Version rollback**: set the previous tag and re-run `make deploy`.
- **Full rollback**: reinstall from a snapshot you keep outside this project
  (the data volume **and** the same `vault.yml`).
- **Config rollback**: `git revert` or edit the per-host vars, then `make
  deploy`.
- **Firewall rollback**: `systemctl disable --now firewall && nft delete
  table inet basefw` (provider console if SSH is affected), then set
  `firewall.enabled: false` and re-run.
- **SSH hardening rollback**: `rm /etc/ssh/sshd_config.d/00-sshd-hardening.conf
  && systemctl reload ssh` (provider console), then set
  `sshd.hardening_enabled: false` and re-run.

## 8. Troubleshooting

| Symptom | Check / action |
|---|---|
| TLS / OIDC not answering | Domain A record resolves to the host; TCP 80/443 open; `docker logs netbird-traefik`. |
| STUN / relay clients fail | UDP 3478 open; Traefik owns `172.30.0.10`. |
| `prometheus-node-exporter` failed after a reboot | The overlay address was never created: the drop-in waits ~90s then gives up (5 retries). Check `docker ps` / `ip -br addr show wt0` / `journalctl -u prometheus-node-exporter`. A manual `systemctl start prometheus-node-exporter` clears it once the overlay is up. |
| Dashboard/API answer locally but not from the internet (firewall applied) | `nft list table inet basefw` — the declared TCP ports must be there (the NetBird agent adds one extra `iifname "wt0" counter … accept` rule of its own; that is expected). `make deploy TAGS=firewall` re-verifies them from the control node. Roll back with `systemctl disable --now firewall && nft delete table inet basefw`. |
| `make deploy TAGS=sshd` failed and the host kept password login | Expected: the role reverted the drop-in and failed. Read the failing task (the key-only login probe is the usual one): the `iac` key must be authorized by `make deploy` and accepted by OpenSSH (`make agent-load` for a `/mnt/c` key). |
| No usable SSH login after enabling hardening | Recover from the provider console: `rm /etc/ssh/sshd_config.d/00-sshd-hardening.conf && systemctl reload ssh`, then set `sshd.hardening_enabled: false` and re-run. |
| Readiness times out on first deploy | GeoLite2 download (§1); re-run or pre-seed the DBs. |
| node-exporter panels show "No data" although the target is up | The push cadence is too slow for the dashboards' 60s `rate()` windows: keep `monitoring.alloy.scrape_interval` at 15s (30s works, 60s yields a single sample per window). Check with `count_over_time(node_load1{instance="<host>"}[5m])` (≈20 points at 15s) and re-run `make deploy TAGS=monitoring`. |
| Tenant run: token rejected | PAT expired — recreate it for the `admin` service user and update the vault (§2). |
| Host reinstalled / reimaged | Two things: delete the stale host-returned keys from `vault.yml` (§2), then deploy with `make deploy REBUILD=1` so the new SSH host key is re-pinned and the cached facts / generated tenant render are dropped. |
| A vault file is unreadable | It must be ansible-vault encrypted; the helpers re-encrypt a plaintext file on the next run. |
| SSH refuses the private key (`UNPROTECTED PRIVATE KEY FILE`, `are too open`) | The shared `scripts/run-with-ssh-agent.sh` starts the pinned Keychain agent, loads the configured keys and retries once automatically. If it still fails, check the `host_*_ssh_privkey_file` paths in the host's `main.yml` and run `make agent-load`. |

Useful commands:

```bash
make print [HOST=<host>]                        # resolved vars incl. vault (HOST optional if single host)
ssh <host> 'cd /opt/netbird && docker compose logs -f netbird-server'
ssh <host> 'cd /opt/netbird && docker compose ps'
```

## 9. Secrets and safety

- Never commit `vault.yml` (gitignored).
- The vault password file is required to decrypt any vault.
- Keep a copy of `vault.yml` (which holds the datastore key) off-host.

## 10. Manual verification on a disposable host

The cases `tests/` cannot cover. Run them on a throwaway host with a throwaway
domain (never a live one): read-only checks first, destructive ones last, and keep
evidence under `/tmp/opencode/test-run-<stamp>/artifacts/<case>/`, redacted. The
expected result is the contract — a deviation is a defect to record, not a reason
to skip.

### Render, proxy, monitoring and security roles

- [ ] Re-run the `management` role: `changed=0`, both containers healthy.
- [ ] Hand-edit `/opt/netbird/config.yaml`, re-run: the file is restored (rendering
      is the source of truth).
- [ ] `server.exposed_port: 8443`: compose publishes `8443:443`, `config.yaml`
      advertises it, the firewall allows it.
- [ ] A moved `server.stack_dir`: the deploy renders there; the project name
      stays pinned.
- [ ] Unset `vault_rhost_setup_key` and run `make monitoring`: fails before
      starting the container and names the variable.
- [ ] `make monitoring` with a key: the peer joins `rhost` with no routes; the
      exporter listens on the overlay only (`ss -lntp`, plus a probe from off-host);
      both CrowdSec units are active and the bouncer is loaded.
- [ ] `monitoring.alloy.enabled: true` with a reachable `loki_push_url`: SSH
      journal events arrive; an unreachable Loki is a warning, not a failure.
- [ ] `firewall.enabled: true`: only 80/TCP, 443/TCP and 3478/UDP (plus SSH and
      WireGuard) are open; the rule set is identical on a re-run.
- [ ] `sshd.hardening_enabled: true` without a keyed login: refuses before writing;
      break the verification on purpose and the config rolls back.
- [ ] Each `sshd.permit_root_login` value matches `sshd -T`.
- [ ] Run each role with an empty and then a pre-filled vault: missing secrets are
      generated once, non-empty values are never rotated, the file stays encrypted
      and `-vvv` shows no value.

### End-to-end

- [ ] `make dry-run` on a fresh host exits 0; a placeholder `ansible_host` is
      refused with `make prep` named.
- [ ] `make deploy`: `iac` created with passwordless sudo and the configured
      keys; a second run changes nothing.
- [ ] `make deploy`: server, dashboard and proxy up; 80/443 and 3478 reachable, the
      certificate valid for the throwaway domain, dashboard 200, API 401, relay
      WebSocket answered.
- [ ] A second `make deploy`: `changed=0` outside the documented non-idempotent
      steps.
- [ ] `make plan` writes nothing; `make apply` converges and a second apply is
      empty; an expired token stops with the Dashboard recovery steps; an invalid
      value fails locally before any API call.
- [ ] `make view` / `make edit`: per-host decrypt, edits stay encrypted
      and sorted, and a save is refused when the vault changed during the edit.
- [ ] `make prep HOST=<name> IP=<addr>`: comment-free scaffold, encrypted
      vault, idempotent; `FORCE=1` replaces the address.
- [ ] `make hostkeys`: refreshes the entries; a changed key is refused with its
      fingerprint and the `FORCE=1` hint; one unreachable host leaves the file
      intact.

### Negative and destructive

- [ ] A plaintext `vault.yml`: the next write re-encrypts it.
- [ ] Kill the agent and exporter containers: they come back on their own; after a
      reboot the overlay binds before the exporter starts.

### Security surface

- [ ] `git ls-files` shows only `example/` under `inventory/host_vars`; `make lint`
      (gitleaks plus the privacy check) is green.
- [ ] The vault on disk is `0600` and encrypted.
- [ ] sudoers: `iac` passwordless, `admin` password sudo, no stray entries.
- [ ] `sshd -T`: password login off after hardening, keyed login works.
- [ ] A `-vvv` run of the secret-bearing playbooks shows no vault value.
- [ ] `docker inspect`: read-only Docker socket, no unnecessary published ports or
      capabilities.
- [ ] No exporter listens on a public or loopback address.

### Convergence and contracts

- [ ] Disable each monitoring component in turn: the units stop and are
      disabled, the Alloy stack is removed, packages are kept; re-enabling restores
      it without reinstalling.
- [ ] A component whose package was never installed is skipped, not failed.
- [ ] `GET /api/peers` returns stable `ip`, `dns_label` and `groups`; the three
      setup keys map to the documented groups; embedded DNS resolves a peer name
      from inside the overlay.
- [ ] `AGENTS.md`, `docs/components/` and this runbook match observed behaviour; a
      contradiction is recorded as a defect.

### CrowdSec engine and blocklist importer

The engine is pinned to `crowdsec_version` (currently 1.8.1) from the packagecloud
bookworm repository; Debian's own trixie package is older. The pre-upgrade backup
is written to `/var/backups/crowdsec-pre-<version>.tgz`.

The optional blocklist importer runs next to the LAPI and is controlled by:

- `crowdsec.blocklist_import.enabled` — deploy the importer;
- `crowdsec.blocklist_import.preset` — `embedded` (~20k high-confidence IPs),
  `server` (conservative server set), or `max` (all feeds);
- `crowdsec.blocklist_import.interval` — seconds between runs;
- `crowdsec.blocklist_import.max_decisions` — total decision cap (`0` = no cap);
- `crowdsec.blocklist_import.batch_size` — API batch size;
- `crowdsec.blocklist_import.decision_duration` — decision TTL;
- `crowdsec.blocklist_import.extra_env` — extra importer environment variables
  (for example per-feed `ENABLE_*` toggles).

Credentials are generated into the host vault as
`vault_crowdsec_blocklist_import_machine_password` and
`vault_crowdsec_blocklist_import_bouncer_key`; the machine account writes decisions and
the bouncer key reads existing decisions for deduplication.
