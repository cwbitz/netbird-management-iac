# Testing plan

How this project is tested: the levels, the environment each level needs, the
rules for recording results, and what counts as done. The executable case list
with IDs, commands and expected results is [matrix.md](matrix.md).

Author a test plan and its matrix **before** running the suite, fill `Status` /
`Evidence` while running it, and write the defect report afterwards. A plan
written from the results is not a plan.

## Scope

Everything the project ships:

- playbooks — `site`, `tenant`, `bootstrap`, `backup`, `restore`, `monitoring`,
  `host_keys`, `ssh_agent_load`, `validate_knobs`;
- roles — `management`, `monitoring`, `agent`, `firewall`, `sshd`, `helpers`;
- helpers — `scripts/audit_example_knobs.py`, `check_host_keys.py`,
  `check_repo_privacy.py`, `ensure_inventory_host.py`,
  `render_clean_template.py`, `sort_vault_keys.py`,
  `validate_tenant_config.py`, `retry-transient.sh`, `run-with-ssh-agent.sh`;
- the Makefile interface, the vault lifecycle, and the contracts documented in
  `AGENTS.md` and `docs/components/`.

## Environment and safety boundaries

- **Live hosts are read-only.** Inspect them with `make print`,
  `make vault-view`, `docker inspect`, `systemctl status` and external
  probes. No deploy, bootstrap, backup, restore, firewall or SSH-hardening run
  targets a live host.
- **Every state-changing or destructive case runs on a disposable
  Debian-family host** (systemd, Docker Engine with Compose v2, nftables, sshd)
  that can be rebuilt from scratch.
- **Isolate the test environment**: its own inventory (never edit the real
  `inventory/hosts.yml`), its own vault password file, its own domain and DNS
  record. Reusing a live domain breaks ACME validation and the STUN contract.
- **Ask before creating resources** — hosts, domains, DNS records — and before
  anything that costs money or touches a system outside the test host.
- **Order of work**: read-only checks first, then state-changing cases, then
  destructive ones. Snapshot or back up before every destructive step.
- **Never print, paste or commit secrets.** Redact evidence before quoting it;
  a secret in a log or a report is itself a defect to record.

## Levels

### L0 — static

The gate every change must pass, deterministic and offline:

- `make lint` — knob validation play, `--syntax-check` on every playbook,
  ansible-lint, the example-knob audit, the host-key check, the repository
  privacy check and the `gitleaks` tree scan;
- `yamllint` (config committed, not wired into `make lint`);
- `shellcheck scripts/*.sh`;
- `python3 -m compileall scripts`;
- negative runs of the audit scripts on a throwaway copy of the tree.

### L1 — unit

The Python and shell helpers have no tests yet. Build `tests/` with pytest
(stdlib `unittest` if adding a dependency is undesirable) and cover, per helper,
the success path, the rejection path and the exit code. Build fixtures in
temporary directories; never read the real inventory, vault or backup tree.
Cover at minimum:

- `validate_tenant_config.py` — every validated field class (names, addresses,
  CIDR, ports, domains, email, references), duplicate detection, and that
  `tenant_strict` defaults to off;
- `sort_vault_keys.py` — ordering, comment preservation, the
  no-op path for a file it cannot normalise, and the line-multiset check;
- `ensure_inventory_host.py` — create, idempotent re-run, `FORCE`, port
  handling;
- `render_clean_template.py` — comment stripping without value damage;
- `audit_example_knobs.py` — example/schema differences in both directions and
  the derived/wiring whitelists;
- `check_host_keys.py` — `known_hosts` parsing, `[host]:port` form, changed-key
  detection, exit codes;
- `check_repo_privacy.py` — protected trees and credential files, allowlisted
  versus live addresses, mailboxes and inventory host names;
- `retry-transient.sh` — retry until the limit, immediate exit on a permanent
  error, exit-code passthrough;
- `run-with-ssh-agent.sh` — behaviour without an agent, and the single retry on
  a refused key.

### L2 — role

One role at a time on the disposable host, with facts and Docker present:

- `management` — rendered files, convergence back to the rendered state after a
  hand edit, container health, TLS;
- `agent` — setup-key resolution, peer group, container health;
- `monitoring` — exporter bind address, CrowdSec units, Alloy containers;
- `firewall` — default deny, the public port contract, control-node
  re-verification, idempotency;
- `sshd` — the refuse-to-lock-out guard, rollback on failed verification, root
  policy variants;
- `helpers` — secret generation, preservation of existing values, encryption at
  rest, `no_log`.

### L3 — end-to-end

The documented operator flow on the disposable host with a test domain:
bootstrap, deploy, external verification (TCP 80/443, UDP 3478, certificate
chain, dashboard, REST API, relay WebSocket), tenant `plan`/`apply`, backup,
restore, `hostkey-init`, vault operations, `host-init`.

Idempotency is part of every L3 case: a second run at the same desired state
reports `changed=0`, except for steps that are inherently non-idempotent (list
them explicitly with the reason).

### L4 — negative and destructive

The paths where the product must fail safely:

- backup with an injected archive failure — the container must end up running;
- restore with a corrupt archive — must fail before stopping the stack;
- restore with a missing or mismatched datastore key — actionable message, data
  untouched;
- a plaintext `vault.yml` — re-encrypted on the next write;
- a missing `vault.yml`, unreachable host, or filled disk;
- an interrupted tenant apply and a transient API failure.

### L5 — security

- no secret in the tree, the index or the history; the vault always encrypted at
  rest;
- `iac` passwordless sudo, `admin` password sudo, effective sshd config;
- container ports, the read-only Docker socket, exporter listeners;
- `no_log` on every secret-handling task, verified with a verbose run;
- `exposed_port` and `stack_dir` consistency across the compose template, the
  rendered `config.yaml`, the firewall contract and the restore play.

### L6 — convergence and contracts

- component toggles converge **off** as well as on;
- a unit that does not exist on the host is skipped, not failed;
- the peer API and embedded DNS match the documented mesh contract.

## Execution rules

- Write the expected result before running a case; never backfill it.
- Cases are independently runnable; declare prerequisites where order matters.
- A defect gets a reproducing case before anything else happens.
- Separate product defects from environment failures, and state the evidence
  for that call.
- Skip only with a recorded reason; never count an unexecuted case as a pass.

## Recording

One row per case in [matrix.md](matrix.md):

| Field | Content |
| --- | --- |
| `ID` | `ST`/`UT`/`RL`/`E2E`/`NEG`/`SEC`/`CNV` plus a number |
| `Status` | `todo`, `pass`, `fail`, `blocked`, `skip` — with a reason for the last two |
| `Evidence` | relative path under the run directory, e.g. `artifacts/E2E-03/` |

Keep raw logs, `-vvv` output, `docker inspect`, `systemctl status` and probe
responses under `/tmp/opencode/test-run-<UTC stamp>/artifacts/<ID>/`. Redact
before quoting; never store a decrypted vault.

## Defects

Severity: `blocker` (data loss, outage, security), `major` (feature unusable, or
docs contradict behaviour), `minor`, `nit`. Each entry carries a minimal
reproduction, expected vs actual, impact, evidence path and a suggested fix.
Merge entries that share a root cause.

## Definition of done

- L0 green; L1 covers the helpers' success and rejection paths;
- L2/L3 critical paths pass on the disposable host and are idempotent on a
  second run;
- every L4 case fails safely with an actionable message;
- L5 has no unexplained high-severity finding;
- every conclusion points at evidence, and every unexecuted case names the
  reason and the condition that would unblock it.

## Prohibitions

- No write operation against a live host; no command that can interrupt it.
- No secret in output, logs, reports or commits.
- No change to the product to make a case pass; no drive-by fixes; no commits or
  pushes.
- No claim of success without evidence.
