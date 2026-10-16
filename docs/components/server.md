# NetBird server (management + signal + relay + STUN)

The combined `netbirdio/netbird-server` container runs everything the control
plane needs:

| Component | Role |
|---|---|
| Management | control plane and REST API (`/api/*`) |
| Signal | peer coordination / connection brokering |
| Relay | fallback traffic relay (`/relay`) |
| STUN | NAT traversal on UDP `3478` |
| Dex IdP | embedded identity provider (see [identity.md](identity.md)) |

Deployed by `roles/management`: it renders `config.yaml` (from
`roles/management/templates/config.yaml.j2`), `dashboard.env`, and
`docker-compose.yml` into `{{ stack_dir }}` (`/opt/netbird`) and applies them with
`community.docker.docker_compose_v2` (see [roles.md](roles.md)). The image is
pinned by `server_version` (Renovate-tracked).

## Rendered `config.yaml`

- `exposedAddress` `https://<domain>:443`; the container listens on `:80` behind
  Traefik (see [traefik.md](traefik.md)).
- `stunPorts: [3478]`; `metricsPort: 9090` and `healthcheckAddress: ":9000"` are
  internal.
- `server.authSecret` — relay auth, base64 **padding stripped**.
- `server.auth.sessionCookieEncryptionKey` — session cookie key (auto-generated
  internal).
- `server.store.encryptionKey` — data-at-rest key. It **must keep base64 padding**
  (Go `base64.StdEncoding`); see [data-and-volumes.md](data-and-volumes.md).
- `server.reverseProxy.trustedHTTPProxies` — the built-in Traefik address, plus
  optional `trustedPeers` for external reverse proxies.
- `server.disableGeoliteUpdate` — see GeoLite2 below.

Keys come from the encrypted per-host vault (`vault_relay_auth_secret`,
`vault_session_cookie_encryption_key`, `vault_datastore_encryption_key`).

## Startup

- Readiness is `https://<domain>/oauth2/.well-known/openid-configuration`; hitting
  it drives the first Let's Encrypt certificate issuance.
- **GeoLite2**: the server downloads MaxMind GeoLite2 DBs from `pkgs.netbird.io` on
  first start and **blocks startup until they finish**; `disableGeoliteUpdate` only
  disables *updates*, not the initial load. On hosts where that CDN is slow the
  readiness wait times out (the container keeps downloading and the DBs persist, so
  a re-run succeeds). For such hosts, pre-seed `GeoLite2-City_*.mmdb` + `geonames_*.db`
  into the `netbird_data` volume and set `disable_geolite_update: true`.
- A bind-mounted config change does **not** recreate the container, so the
  `config.yaml` / `dashboard.env` template tasks notify the `[NetBird] Restart the
  stack` handler.

## First-owner bootstrap

`/api/setup` is unauthenticated and works only while the instance has **no
accounts**, so the owner-bootstrap tasks run on the first deploy and are skipped
afterwards. With `owner_email` set the role requests a short-lived owner token
(`create_pat`, 7 days), creates the `admin` service user and a PAT for it
(`vault_admin_service_user_access_token`), then deletes the owner token. The owner
token is never written to disk or logged. Without `owner_email`, onboard manually
at `https://<domain>/setup`.
