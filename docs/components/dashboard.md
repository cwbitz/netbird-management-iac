# Dashboard

The NetBird web UI runs as the `netbirdio/dashboard` container, routed by Traefik
at `Host(<domain>)` (see [traefik.md](traefik.md)). Upstream publishes only moving
tags (`latest` / `sha-*` / `pr-*`), so `dashboard_version` is `latest` and cannot
be pinned or tracked by Renovate.

`roles/management` renders `dashboard.env`
(`roles/management/templates/dashboard.env.j2`):

- Management API + gRPC endpoints point at `https://<domain>`.
- Auth uses the embedded Dex IdP: authority `https://<domain>/oauth2`, client
  `netbird-dashboard`, scopes `openid profile email groups`, redirect `/nb-auth`
  and silent redirect `/nb-silent-auth` (see [identity.md](identity.md)).
- TLS is terminated by the bundled Traefik, so `NGINX_SSL_PORT=443` and
  `LETSENCRYPT_DOMAIN=none`.
