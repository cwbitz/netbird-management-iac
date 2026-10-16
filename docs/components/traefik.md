# Traefik (built-in reverse proxy)

The stack bundles a Traefik reverse proxy that terminates TLS for the dashboard
and the server:

- Automatic Let's Encrypt certificates over **TLS-ALPN** (the `websecure`
  entrypoint sets `allowACMEByPass`); ACME state lives in the
  `traefik_letsencrypt` volume.
- `web` (80) redirects to `websecure` (443).
- Routers: `netbird-dashboard` (`Host(<domain>)`), `netbird-grpc` (h2c backend),
  and `netbird-backend` (relay / WebSocket / API / OAuth2). gRPC timeouts are
  disabled for long-lived streams.
- It owns `172.30.0.10` in the `netbird` bridge network
  (see [networking.md](networking.md)) and is the only reverse-proxy address
  management trusts (`reverseProxy.trustedHTTPProxies`).

The image is pinned by `traefik_version` (Renovate-tracked). External reverse
proxies are supported through `trusted_peers` (an extra trusted proxy address per
entry).
