# Host firewall

`roles/firewall/` — the host's **base firewall**: default-deny inbound, applied
as a dedicated nftables table (`inet basefw`) and persisted by a oneshot systemd
unit. Opt-in per host (`firewall_enabled`, off by default). Reached via
`make deploy TAGS=firewall` or `playbooks/site.yml`. Debian-family only.

## Why

The server host runs on a public VPS and Docker publishes its ports on
`0.0.0.0`. The mesh contract is only three ports — see
[`networking.md`](networking.md) — but everything else the stack exposes
(the management API's container ports, the dashboard backend, the Docker socket
proxy, …) is meant to be reached through Traefik or the overlay, never directly.
`crowdsec-firewall-bouncer` is not a base firewall: it only enforces CrowdSec
decisions. A default-deny table is.

It is **opt-in** because it is the one role that can take the mesh off the
internet if the contract is wrong; when it is on, the declared ports are
re-verified from the control node after applying.

## Port matrix

| Port | Proto | Why it stays open |
|---|---|---|
| — | — | `iif lo`, plus `ct state established,related` (ACME, DNS, image pulls, apt, GeoLite2) |
| `wt0` | — | the overlay: only authenticated mesh peers can appear there |
| `firewall_netbird_wg_port` (51820) | UDP | the overlay's WireGuard port, so direct P2P paths keep working (before any conntrack rule) |
| `firewall_ssh_port` (inventory `ansible_port`, then 22) | TCP | SSH (CrowdSec bans the brute force when `monitoring_enabled`) |
| 80 | TCP | Traefik: ACME TLS-ALPN-01 + HTTP→HTTPS redirect |
| `exposed_port` (443) | TCP | Traefik: dashboard, REST API/gRPC, OAuth2, relay WebSocket |
| `stun_port` (3478) | UDP | STUN/TURN of the signal/relay service |
| ICMP/ICMPv6 | — | path-MTU discovery, diagnostics (`firewall_allow_icmp`) |

The public lists are knobs (`firewall_public_tcp_ports` /
`..._udp_ports`) defaulting to that contract; `exposed_port` and `stun_port` come
from the server role (`roles/management/defaults/main.yml`), and Traefik's 80 is
literal in the compose template — keep them in step when you change either.

## How

A **dedicated table** with an `input` hook, policy `drop`, so nothing else is
flushed or replaced: Docker owns `ip/ip6 filter`+`nat`, CrowdSec owns
`ip crowdsec`, NetBird owns `ip netbird`. An `inet` `drop` is terminal, so the
default-deny holds even though Docker's `ip`-filter `INPUT` chain keeps policy
`accept` — which is also why the overlay is accepted here explicitly. The
`FORWARD` path is left to Docker/NetBird.

The **NetBird agent also writes one rule into this table**: when the overlay comes
up it inserts `iifname "wt0" counter … accept` at the top of the `input` chain and
re-inserts it whenever it is missing (its nftables manager reconciles
periodically). That rule is redundant with the `wt0` accept below, so
`nft list table inet basefw` normally shows **one rule more than the rendered
file** — expected, not drift. Reproving the role (`make deploy TAGS=firewall`,
which recreates the table) does not break the overlay: the agent re-adds its rule
and the template's own `wt0` accept keeps the tunnel up in the meantime.

The overlay and the WireGuard port are accepted **before** any conntrack-state
rule: the kernel's WireGuard bypasses the netfilter output hook, so its return
traffic has no prior conntrack entry and can be classified `invalid`; a
`ct state invalid drop` above these accepts would break the tunnel.

## Safety and verification

1. The rendered ruleset is validated with `nft -c` **before** it is applied.
2. The unit re-validates (`ExecStartPre`) on every start, so a syntax error can
   never leave the host unfirewalled.
3. After applying, the SSH connection is re-checked (`wait_for_connection`), so a
   mistake fails loudly instead of silently locking the operator out.
4. Once the stack is running locally (`netbird-traefik` up), every declared
   public **TCP** port must still answer from the control node. This is the check
   that catches a wrong matrix before the mesh is silently cut off. On a host
   where the stack is not deployed yet it is skipped by design.

UDP cannot be probed this way (STUN/TURN): declare `stun_port` correctly and
verify from a client (`netbird status`).

## Persistence and rollback

The ruleset is rendered to `/etc/nftables.d/90-firewall.nft` and loaded by
the Ansible-managed oneshot unit `firewall.service`. It never enables
Debian's `nftables.service` (whose stock config does `flush ruleset`, which would
race with Docker/CrowdSec/NetBird at boot).

```bash
# Revert to no base firewall on the host:
ssh <host> 'systemctl disable --now firewall && nft delete table inet basefw'
```

Then set `firewall_enabled: false` in the host's `main.yml` so a later deploy
does not re-apply it.

## See also

[`networking.md`](networking.md) (the port contract), [`sshd-hardening.md`](sshd-hardening.md),
[`server.md`](server.md), [`RUNBOOK.md`](../RUNBOOK.md).
