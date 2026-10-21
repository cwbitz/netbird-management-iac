# Data & volumes

Config files are rendered to `{{ stack_dir }}` (`/opt/netbird`, set per host
in `inventory/host_vars/<hostname>/main.yml`). Two named Docker
volumes hold state (explicit names keep them stable regardless of the compose
project directory):

| Volume | Mount | Contents |
|---|---|---|
| `netbird_data` | `/var/lib/netbird` | `store.db`, `idp.db`, `events.db`, GeoLite2 DBs |
| `traefik_letsencrypt` | `/letsencrypt` | `acme.json` |

## Encryption keys (`vault.yml`)

- `vault_datastore_encryption_key` → `server.store.encryptionKey`. **Must keep base64
  padding** (Go `base64.StdEncoding`). It is **not** in the backup archive, and a
  restore must reuse the same value or the encrypted user data is unrecoverable.
- `vault_session_cookie_encryption_key` → `server.auth.sessionCookieEncryptionKey`
  (auto-generated internal).
- `vault_relay_auth_secret` → `server.authSecret`, base64 padding **stripped**.

## Backup & restore

`make backup` stops the container, snapshots the `netbird_data` volume to
`backup/<host>/<stamp>/netbird_data.tgz`, and restarts it; `make restore` replaces
the volume and redeploys. The datastore key stays in the control node's `vault.yml`,
so back that file up separately. Full procedure: [../RUNBOOK.md](../RUNBOOK.md).
