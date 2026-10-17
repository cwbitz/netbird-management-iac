# Tenant configuration as code

`playbooks/tenant.yml` applies the declarative NetBird account state against the
running server's REST API via the `community.ansible_netbird` collection. Desired
state is Ansible variables in the per-host vars: non-secret in
`inventory/host_vars/<host>/main.yml`, secret/PII in `vault.yml`, using the
collection's native names:

`netbird_settings`, `netbird_groups`, `netbird_posture_checks`,
`netbird_policies`, `netbird_dns_nameserver_groups`, `netbird_dns_zones`,
`netbird_dns_disabled_management_groups`, `netbird_networks`,
`netbird_setup_keys`, `netbird_services` + `netbird_service_domains`,
`netbird_users` / `netbird_service_users`.

The collection's `configure` role reads raw YAML (no templating), so the play
renders the variables into a generated, gitignored directory
(`.cache/tenant_config/<host>/`) and passes it as `config_dir`; `commit` / `strict`
come from `tenant_commit` / `tenant_strict` (both default `false` = preview).
Plain names are resolved to IDs. Users/service users use the separate
`netbird_user` module (applied afterwards) and their `auto_groups` take plain group
names.

**Convention exception:** within `netbird_settings` the peer expiry durations use
`peer_login_expire_seconds` / `peer_inactivity_expire_seconds`, which
`playbooks/tenant.yml` maps to the collection's `peer_login_expiration` /
`peer_inactivity_expiration` fields when rendering; the `*_expiration_enabled`
toggles keep the collection names.

Requires a valid `vault_service_admin_access_token` (see `AGENTS.md`).

## Collection gotchas

- `netbird_networks.routers` needs an enrolled peer, and `netbird_services` /
  `netbird_service_domains` need a registered reverse-proxy cluster, which only the
  self-hosted proxy software itself can create (`BYOP`); the collection can only
  delete one. Unset options are skipped.
- Setup keys: the collection preflight requires `expires_in > 0` (max `31536000`),
  so a **never-expiring** key (`expires_in: 0`) cannot be declared in
  `netbird_setup_keys`; create one once out-of-band. New secrets are persisted as
  `vault_<setup-key-name>`.
- Routed networks bind their gateway by peer **group** (`routers[].peer_groups`,
  e.g. `home-router`), not by an individual peer name. The group is created by the
  tenant play and the client's setup key auto-assigns it, so a network applies on
  the **first** run (no chicken-and-egg); the client becomes its routing peer when
  it enrolls. Pinning `routers[].peer` by name needs an already-enrolled peer.
- Exit nodes: a `0.0.0.0/0` (and `::/0`) network resource routed via a peer needs
  `masquerade: true` on the router, an accept policy from the using group to the
  routing peer's group (declare one — `strict` removes the built-in `Default`
  rule), and IP forwarding on the peer. **Auto Apply** (v0.55.0+, default on) is a
  Dashboard/client setting the API/collection cannot express.
- Edition boundaries (self-hosted): core (groups, policies, posture checks, DNS,
  networks, setup keys, users, settings) is open source; SCIM/IdP provisioning,
  audit/SIEM streaming, MDM/EDR, HA and MSP/multi-tenant require an Enterprise
  license. Agent Network is a separate self-hosted deployment and is not managed
  here.
