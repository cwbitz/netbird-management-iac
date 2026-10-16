# Roles & playbooks

## Playbooks

- `playbooks/site.yml` — server preflight + the `management` role.
- `playbooks/tenant.yml` — tenant config-as-code on `localhost` against the server
  API (see [tenant-config.md](tenant-config.md)).
- `playbooks/bootstrap.yml` — optional, opt-in host tuning (APT/Docker mirrors,
  Docker install, SSH service account); never runs as part of `site.yml`.
- `playbooks/backup.yml` / `playbooks/restore.yml` — volume snapshot and paired
  restore.
- `playbooks/monitoring.yml` — optional host monitoring + host security.
- `playbooks/host_keys.yml` / `ssh_agent_load.yml` — control-node SSH helpers.

## Roles

- `roles/management/` — the deploy: preflight, secret provisioning, config
  rendering, `docker_compose_v2`, TLS readiness, first-owner bootstrap (see
  [server.md](server.md)). `defaults/main.yml` holds every image tag behind a
  `_version` var.
- `roles/agent/` — runs the NetBird agent container (`agent_dir` =
  `/opt/netbird-agent`) so the host joins the overlay; used by `roles/monitoring`
  (no standalone playbook). `peer_setup_key` decides the peer's group.
- `roles/monitoring/` — optional, opt-in (`make monitoring`): apt-installs
  `prometheus-node-exporter` + `crowdsec` + `crowdsec-firewall-bouncer` on a
  Debian-family host and includes the `agent` role; skipped unless
  `monitoring_enabled: true`. The play sets `gather_facts: false` and the role
  gathers facts itself, so non-opted hosts are never contacted.
- `roles/helpers/` — a real role (no `tasks/main.yml`), always invoked via
  `include_role` + `tasks_from`: `control_node_prereqs.yml`, `install_docker.yml`,
  `read_vault.yml` / `write_vault.yml`, and
  `dispatch_secrets.yml` / `generate_secrets.yml` / `store_secret.yml`.

## Supported platform

Debian-family Linux with Docker Engine + Compose v2. When Docker is missing the
preflight installs Docker CE via Docker's official install script
(`https://get.docker.com`; disable with `install_docker: false`, which then fails
with install guidance). Non-Debian support is best-effort; automatic install is
Debian-only.

## Image version baseline

Every tag is a role-default var carrying a
`# renovate: datasource=docker depName=<image>` annotation so Renovate keeps it
current (see `renovate.json`).

| Component | Registry | Version var |
|---|---|---|
| netbird-server | dockerhub | `server_version` |
| netbird-dashboard | dockerhub | `dashboard_version` (upstream has no pinned tags) |
| traefik | dockerhub | `traefik_version` |
| netbird-agent | ghcr.io | `netbird_agent_version` |
| alloy | dockerhub | `alloy_version` |
