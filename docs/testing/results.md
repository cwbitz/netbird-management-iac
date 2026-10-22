# Test run 2026-10-22 (L0–L1)

First execution of [plan.md](plan.md) against [matrix.md](matrix.md). Static and
unit layers only; the host-level layers need a disposable host and are recorded
in the next run.

| Field | Value |
| --- | --- |
| Date (UTC) | 2026-10-22 |
| Scope | L0 (static), L1 (unit) |
| Control node | Ubuntu, ansible-core 2.19.11, ansible-lint 26.6.0, Python 3.11.15 |
| Run directory | `/tmp/opencode/test-run-20261022T045839Z/` |
| Result | 30 cases executed: 26 pass, 4 skip, 0 fail |

## Summary

| Layer | Cases | Pass | Skip | Fail |
| --- | --- | --- | --- | --- |
| L0 static | 12 | 12 | 0 | 0 |
| L1 unit | 18 | 14 | 4 | 0 |
| Total | 30 | 26 | 4 | 0 |

## L0 — static

| ID | Outcome | Evidence |
| --- | --- | --- |
| ST-01 | `make lint` exit 0; ansible-lint 30 files, 0 findings; knob audit OK (42 knobs); host-key check OK; privacy guard OK | `artifacts/ST-01/` |
| ST-02 | `yamllint .` exit 0, no finding | `artifacts/ST-02/` |
| ST-03 | `shellcheck scripts/*.sh` (0.11.0) exit 0, no finding | `artifacts/ST-03/` |
| ST-04 | `compileall` exit 0 | `artifacts/ST-04/` |
| ST-05 | `make help` lists exactly the 16 public targets; `lint`, `validate-knobs`, `agent-*`, `keychain-*`, `ensure-*`, `verify-keychain-pin` hidden | `artifacts/ST-05/` |
| ST-06 | Removing a key from the example fails with both the schema and the playbook-knob message, naming the key | `artifacts/ST-06/` |
| ST-07 | A schema-only key fails, naming the key | `artifacts/ST-07/` |
| ST-08 | A drifted role default fails, naming the key, both values and the source file | `artifacts/ST-08/` |
| ST-09 | `make validate-knobs` with a missing inventory prints the skip notice and exits 0 without running a play | `artifacts/ST-09/` |
| ST-10 | `--syntax-check` exit 0 on all six playbooks | `artifacts/ST-10/` |
| ST-11 | The privacy guard fails on a force-added host directory and passes once it leaves the index | `artifacts/ST-11/` |
| ST-12 | `ansible-inventory --list` on `ci/inventory.yml`: one placeholder host, no warning | `artifacts/ST-12/` |

## L1 — unit

63 pytest cases in `tests/`, run by `make test`:

| Matrix IDs | Module |
| --- | --- |
| UT-01..UT-03 | `tests/test_validate_tenant_config.py` |
| UT-05, UT-07 | `tests/test_sort_vault_keys.py` |
| UT-08..UT-10 | `tests/test_ensure_inventory_host.py` |
| UT-11 | `tests/test_render_clean_template.py` |
| UT-12, UT-13 | `tests/test_audit_example_knobs.py` |
| UT-16..UT-18 | `tests/test_shell_helpers.py` |

Skipped, with the reason recorded in the matrix:

- **UT-04** — `tenant_strict` is decided in the playbook, not by the value gate;
  it belongs to E2E-11.
- **UT-06** — there is no silent no-op path: an unnormalisable vault file is
  refused (exit 1, file untouched). The already-sorted and no-key cases are
  covered instead.
- **UT-14, UT-15** — `check_host_keys.py` is a lint guard against disabled host-key
  verification, not a `known_hosts` parser. Parsing and changed-key detection are
  shell logic in `hostkey-init`, covered by E2E-18..E2E-20.

The matrix rows for these four cases are corrected to match the implementation.

## Findings

No product defect. Four observations:

1. **O-1 — yamllint and shellcheck are not gated.** Both pass, but neither runs
   in `make lint` or CI, so a regression would not be caught. Wire them in (the
   `.yamllint` config already exists; shellcheck needs a pin).
2. **O-2 — the host-key guard scans untracked files too.** The new unit tests
   tripped it because their fixtures contained a literal disabled-checking line.
   The fixtures now compose the strings at run time; the guard stays strict.
3. **O-3 — the matrix assumed a `known_hosts` parser that does not exist.** See
   UT-14/UT-15. `check_host_keys.py` and `hostkey-init` are separate mechanisms; a
   future revision could move the parsing into the script so it can be unit-tested
   without a host.
4. **O-4 — the value gate is the only helper with broad behavioural coverage
   today.** It is the most complex helper (558 lines) and the one most exposed to
   operator input, so this coverage also gives the most value.

## Environment changes made for this run

- `pytest 9.1.1` pinned in `.tool-versions` (`pipx:` backend) and `make test`
  added; CI runs it after `make lint`.
- `.pytest_cache/` ignored.
- `shellcheck 0.11.0` was installed ad hoc through mise for ST-03 and is not
  pinned; see O-1.

## Next

L2–L6 (roles, end-to-end, destructive, security, convergence) need the
disposable host and are not part of this run.

## Host run 2026-10-22 (L2–L6, partial)

Ran against `rs-jp-tyo-1` after the operator confirmed a rebuild. Access was
restored with `make hostkey-init FORCE=1`, then bootstrap, deploy, plan, apply and
backup. The run stopped at the backup step because of a blocking defect; the
destructive cases need the fix first.

### What the deploy reached

| Check | Result | Evidence |
| --- | --- | --- |
| Bootstrap on a rebuilt host | `iac` and `admin` created, keys authorized, Docker installed | `artifacts/E2E-03/` |
| `make dry-run` on a fresh host | exit 0 | `artifacts/E2E-06/` |
| First `make deploy` | server, TLS, owner bootstrap, firewall and SSH hardening converged; the tenant step failed on a permission error | `artifacts/E2E-04/deploy-1.log` |
| Second `make deploy` | exit 0, tenant applied | `artifacts/E2E-07/deploy-2.log` |
| External contract | 80/443 open, TLS 1.3 certificate valid to 2027-01-20, dashboard 200, API 401 unauthenticated, STUN binding answered | `artifacts/E2E-05/probes/external-after.txt` |
| `make plan` | 0 changed, 26 unchanged resources | `artifacts/E2E-08/plan.log` |
| `make apply` | exit 0 | `artifacts/E2E-09/apply-1.log` |
| `make backup` | **failed** in the fetch step; the server container was restarted by the `always:` block | `artifacts/E2E-16/backup.log` |
| Firewall contract | default drop; only 47616/tcp, 80/tcp, 443/tcp, 3478/udp, 51820/udp and the overlay are allowed | `artifacts/RL-12/` |
| SSH hardening | `permitrootlogin no`, password login off, keyed login survived the run | `artifacts/SEC-05/` |
| Sudo policy | `iac` NOPASSWD, `admin` password sudo | `artifacts/SEC-04/` |
| Rendered file modes | `/opt/netbird` 0755, `config.yaml` and `dashboard.env` 0600 | `artifacts/SEC-04/host-security-root.txt` |
| Docker socket | mounted read-only | `artifacts/SEC-04/host-security-2.txt` |

### Defects

**D-1 — fixed, blocker: control-node-local tasks escalated to root.**

`ansible_become` is a connection variable and wins over the `become: false`
keyword, so every delegated-to-localhost task inside a become-enabled play ran as
root. Consequences in one deploy:

- the encrypted vault was rewritten as `root:root 0600`, and the following
  `tenant.yml` step (which reads it as the operator) failed with
  `Permission denied`;
- `backup.yml` created `backup/<host>/<stamp>/` as root, so `fetch` (which always
  writes as the controller user) failed (D-3).

Fix: every control-node-local task now also sets `vars: ansible_become: false`
(helpers vault read/write/store, dispatch and generation, control-node
prerequisites, the firewall's local verification, and the local tasks of
`site.yml`, `bootstrap.yml`, `host_keys.yml`, `ssh_agent_load.yml`,
`backup.yml`, `restore.yml`). Minimal reproduction and the post-fix result:
`artifacts/E2E-04/defect/` — same play, now an `ubuntu`-owned file.

Verified after the fix: `make deploy` completes with the vault staying
`ubuntu:ubuntu 0600` (`artifacts/E2E-07/deploy-3.log`), and `make backup`
succeeds.

**D-2 — open, minor: the firewall legacy-table cleanup always reports changed.**

`roles/firewall/tasks/main.yml` drops `firewall_legacy_tables` with
`changed_when: true` and `failed_when: false`, so a converged host reports one
change per run. Evidence: `artifacts/E2E-07/deploy-2.log`.

**D-3 — fixed, blocker: `make backup` could not fetch the archive.**

Same cause as D-1. After the fix the archive is fetched to
`backup/<host>/<stamp>/` (28 MB, 6 entries, `ubuntu:ubuntu`) and the container is
running: `artifacts/E2E-16/backup-2.log`.

**D-4 — open, minor: the bootstrap probe always reports changed.**

`[Probe] Register the probed identity on the target host` reports `changed` on
every run, so bootstrap is never fully idempotent. Evidence:
`artifacts/E2E-07/deploy-2.log`.

### Backup and restore

`make backup` → `backup/rs-jp-tyo-1/20261022T140955/` (28 MB, 6 entries), server
container running afterwards. `make restore FROM=...` exited 0 and the stack was
redeployed with the current vault key. After the restore the external contract is
intact (80/443 open, TLS 1.3, dashboard 200, API 401 unauthenticated, STUN
answered), `make plan` reports 0 changed / 26 unchanged, and the vault is still
`ubuntu:ubuntu 0600`. Evidence: `artifacts/E2E-17/`.

### Idempotency reading

The second and third `make deploy` runs report `changed=1` for the site play (D-2)
and six changes for the tenant play, all local temporary files that are deleted
and re-rendered at the start of every run; the API diff in `make plan` is 0
changed. The server converges; the `changed` counter does not (D-2, D-4).

### Monitoring

`make monitoring` installs the exporter and CrowdSec on the host and joins the
overlay through the agent. With `alloy_enabled: false` the stack converges:
`prometheus-node-exporter`, `crowdsec` and `crowdsec-firewall-bouncer` are active,
and the exporter listens on the overlay address only (`100.125.231.160:9100`, no
local or public listener) — `artifacts/RL-09/`, `artifacts/RL-10/`,
`artifacts/SEC-08/`.

`alloy_enabled: true` currently fails: `loki_push_url` is an overlay IP literal
(`http://100.125.55.195:3100`) and the central Loki does not answer from this
rebuilt host (`No route to host`). The role's own message recommends the central
peer's NetBird name instead of an IP; RL-11 stays blocked on the operator fixing
that address. The host configuration was restored to its original values after
the run.

Convergence behaves as documented: disabling one component stops and disables
only that unit; disabling the master switch stops and disables both CrowdSec units
and the exporter, keeps the packages installed and skips the absent Alloy stack;
re-enabling brings everything back without reinstalling. Evidence:
`artifacts/CNV-01/`, `artifacts/CNV-02/`, `artifacts/CNV-03/`.

### Negative and destructive cases

| Case | Result | Evidence |
| --- | --- | --- |
| Backup with a broken archive step | The play fails, the server container is restarted by the `always:` block | `artifacts/NEG-01/` |
| Restore with a corrupt archive | Fails at the readability check before stopping the stack; dashboard stays 200 | `artifacts/NEG-02/` |
| Restore with an empty datastore key | **Fails the restore contract** — see D-5 | `artifacts/NEG-03/` |
| Restore without a source | Usage message, exit 2 | `artifacts/NEG-04/` |
| Killing the containers | `docker kill` leaves the stack down (Docker treats it as a manual stop); recovered with `docker compose up -d`. A PID 1 crash could not be forced inside the container, so self-healing stays unverified | `artifacts/NEG-05/` |
| Plaintext vault | The next write encrypts it, keeps mode 0600 and the new content | `artifacts/NEG-07/` |

**D-5 — blocker: restore silently regenerates a missing datastore key.**

Restoring with an empty `vault_datastore_encryption_key` replaces the data volume
first; the redeploy then provisions the "missing" secret, generating a new key
and rewriting the vault. The restored data is encrypted with the old key, so the
server comes up with an empty store, the tenant token is rejected and the data is
unreadable — the exact opposite of the documented guarantee. Recovery required
restoring the original key from the pre-rebuild vault copy and re-running the
restore.

Fix direction: `restore.yml` must assert the datastore key is present (and not
regenerate it) before stopping the stack or replacing the volume.

### Contracts and remaining security

- Peer API returns `ip`, `dns_label` and `groups`; the server peer is in `endpoint`
  (`artifacts/CNV-05/`).
- Setup-key to group mapping matches the documented contract for all three keys
  (`artifacts/CNV-06/`).
- Embedded DNS resolves `rs-jp-tyo-1.netbird.selfhosted` to its overlay address
  from inside the agent container (`artifacts/CNV-07/`).
- The tenant value gate rejects an unknown setting locally, with one message per
  field (`artifacts/E2E-12/`).
- A rejected token stops with the exact Dashboard recovery steps
  (`artifacts/SEC-10/`, also recorded as E2E-13).
- A `-vvv` check run of `site.yml` contains none of the vault secret values
  (`artifacts/SEC-06/`).

**D-6 — minor: the preflight failure message prints template placeholders.**

The placeholder-address assert builds `fail_msg` with single braces, so the
operator sees the literal `{ item }` and `{ hostvars[item].ansible_host }` instead
of the host name and value. Evidence: `artifacts/E2E-01/`.

### Remaining cases (second pass)

| Case | Result | Evidence |
| --- | --- | --- |
| Draw a recovery line for the owner identity | The first owner is now defined once, by the `netbird_users` entry with `role: owner`; the role derives the bootstrap identity from it and the example, schema and audit follow | `roles/management/defaults/main.yml` |
| Rendering the role again | `changed=0`, all containers running | `artifacts/RL-01/` |
| Dashboard and proxy wiring | Dashboard 200 through the proxy; `dashboard.env` holds only the documented keys | `artifacts/RL-03/` |
| Changing `exposed_port` | Converges in one run: firewall first, stack on 8443, TLS check on the published port; external 8443 is blocked upstream by the provider | `artifacts/D-7/` |
| Changing `stack_dir` | Converges in one run with the project name pinned; reverted to `/opt/netbird` cleanly | `artifacts/D-8/` |
| Agent without a setup key | Refuses with the variable name and the fix, container untouched | `artifacts/RL-07/` |
| SSH hardening without a key | Refuses before writing; effective config unchanged | `artifacts/RL-15/` |
| Host-key refresh with a partial failure | Unreachable host reported, the reachable host refreshed, `known_hosts` intact | `artifacts/E2E-20/` |
| Vault view and edit | Content unchanged and still sorted when the editor makes no edit; both encrypted | `artifacts/E2E-21/` |
| Host scaffold | Comment-free, vault encrypted, idempotent, `FORCE` replaces the address | `artifacts/E2E-22/` |

**D-7 — fixed: `exposed_port` converges in one run.**

The TLS self-check now requests the published port, and the firewall rules are
applied before the stack restarts (its reachability check moved to
`firewall/tasks/verify.yml` and runs after). One run moved the stack to 8443 with
the advertised address and the rules following, and one run moved it back to 443;
the dashboard stayed reachable on the restored port. The verification step still
fails when the provider does not forward the new port — this host only forwards
80/443/3478, which is an environment limit, not a project one.

**D-8 — fixed: `stack_dir` can move on a running host.**

The server, monitoring and agent compose calls now pin their project names, so the
directory no longer decides the project identity. Moving the stack to
`/opt/netbird-test` and back completed in single runs with the same containers and
volumes, and the reverted directory is the one the containers run from.

**D-2 and D-4 — fixed.** The firewall lists the loaded tables before deleting a
legacy one, and the bootstrap probe reports its fact registration unchanged, so a
converged `make deploy` now shows `changed=0` for the site play.

**D-5 and D-6 — fixed and verified.** Restore with an empty key now stops at a new
assert before the stack is touched (key hash unchanged, containers still up,
dashboard 200: `artifacts/NEG-03/run-fixed.log`), and the placeholder preflight
renders the host name and the value (`artifacts/E2E-01/run-fixed.log`).

### Still open

Strict-mode tenant deletion (E2E-11), the reboot and interrupted-run cases
(NEG-06/NEG-10), the Alloy path (RL-11, blocked on the central Loki address), the
`docker kill` self-healing question (NEG-05), the firewall precondition case
(RL-14, no such guard exists) and the SSH rollback drill (RL-16, needs a
deliberately broken post-hardening login). Outside-port reachability depends on
the provider forwarding the port, which this host does only for 80/443/3478.

## Post-run defect 2026-10-22 19:14

**D-9 — fixed: the SSH key-only probe ran as root.**

After another host rebuild, `make deploy` failed with `Error 2` at
`[SSHD] Fail when the key-only login did not work`: the probe's
`delegate_to: localhost` inherited `ansible_become`, so it ran as root and read
`/root/.ssh/known_hosts`, which `make hostkey-init` never refreshes. With
`StrictHostKeyChecking=accept-new` an unknown key is accepted, so a first deploy
succeeds, but a rebuilt host presents a changed key and the probe aborts (exit
255); the role correctly rolled the hardening back and failed the run.

The probe now overrides `ansible_become: false`. Verified: `make deploy TAGS=sshd`
applied the hardening (`permitrootlogin no`, password login off), a full
`make deploy` exited 0, the tenant applied, and `make plan` reports 0 changed.
