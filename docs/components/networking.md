# Networking & port contract

## Host reachability (open before deploy)

The public domain's A record must point at the host, and these ports must be open
**before** the first deploy, or Let's Encrypt (TLS-ALPN) and STUN will fail:

| Port | Proto | Purpose |
|---|---|---|
| 80 | TCP | ACME (TLS-ALPN-01) + HTTP→HTTPS redirect |
| 443 | TCP | dashboard, REST API, gRPC, OAuth2 |
| 3478 | UDP | STUN |

Defaults live in `roles/management/defaults/main.yml`
(`http_protocol`, `exposed_port`, `stun_port`).

## Container network

The stack uses a dedicated Docker bridge network `netbird`
(`172.30.0.0/24`, gateway `172.30.0.1`); Traefik is pinned to `172.30.0.10`, the
only proxy address management trusts (see [traefik.md](traefik.md)). Names are
role constants: `network_name`, `network_subnet`, `network_gateway`, `traefik_ip`.

## Overlay

Peers join the overlay with a setup key; the monitoring host joins as the route-less
`endpoint` peer (see [roles.md](roles.md)). The overlay's embedded DNS domain and
address ranges are account settings (`netbird_settings`): keep `dns_domain`
non-public, and note `network_range` re-allocates all peer IPs when changed.
Routed networks and exit nodes are tenant config — see
[tenant-config.md](tenant-config.md).
