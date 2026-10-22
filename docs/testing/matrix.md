# Test matrix

The executable case list for [plan.md](plan.md). `Status` starts as `todo`;
during a run it becomes `pass`, `fail`, `blocked` or `skip`, with the reason for
the last two and a path under `artifacts/<ID>/` in `Evidence`.

Placeholders: `<host>` a disposable test host, `<stamp>` a backup timestamp,
`<test-domain>` a throwaway domain, `<run>` the run directory
`/tmp/opencode/test-run-<UTC stamp>`.

## L0 — static

| ID | Case | Precondition | Action | Expected | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| ST-01 | Lint gate | Clean tree | `make lint` | Exit 0; playbook validation, ansible-lint, the audit, the host-key check and the privacy guard all pass | pass | artifacts/ST-01/ |
| ST-02 | YAML style | Clean tree | `yamllint .` with the committed config | No finding outside `collections/`, `.ansible/`, `.cache/` | pass | artifacts/ST-02/ |
| ST-03 | Shell style | `shellcheck` installed | `shellcheck scripts/*.sh` | No finding | pass | artifacts/ST-03/ |
| ST-04 | Python syntax | Python 3 | `python3 -m compileall -q scripts` | Exit 0 | pass | artifacts/ST-04/ |
| ST-05 | Help surface | Clean tree | `make help` | Public targets documented; internal helpers hidden; every line matches a real target | pass | artifacts/ST-05/ |
| ST-06 | Knob audit: example key absent from schema | Throwaway copy | Remove one key from the copy's example, run `audit_example_knobs.py` | Exit 1, message names the key and both files | pass | artifacts/ST-06/ |
| ST-07 | Knob audit: schema key absent from example | Throwaway copy | Add one key to the copy's schema only | Exit 1, message names the key | pass | artifacts/ST-07/ |
| ST-08 | Knob audit: documented default drifts | Throwaway copy | Change one role default away from the example value | Exit 1, message names the key and the default | pass | artifacts/ST-08/ |
| ST-09 | Knob validation without inventory | No `inventory/hosts.yml` | `make validate-knobs` | Prints the skip notice, exit 0, no play runs | pass | artifacts/ST-09/ |
| ST-10 | Syntax check | Collections installed | `--syntax-check` on all six entry playbooks | All clean | pass | artifacts/ST-10/ |
| ST-11 | Inventory privacy guard | Clean tree | `git add -f` a dummy `host_vars/<other>/main.yml`, run `make lint` | Fails naming the tracked path; guard passes after the file leaves the index | pass | artifacts/ST-11/ |
| ST-12 | Inventory listing | `ci/inventory.yml` | `ansible-inventory --list` against it | Single placeholder host, no warning | pass | artifacts/ST-12/ |

## L1 — unit

| ID | Case | Precondition | Action | Expected | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| UT-01 | Tenant config: minimal valid state | Test fixture | Run the value gate on a minimal valid state | Pass, no finding | pass | artifacts/L1/pytest.log · tests/test_validate_tenant_config.py |
| UT-02 | Tenant config: each invalid field class | Test fixture | One case per class — group name, IPv4/CIDR, port and port range, domain, email, enum | Each fails with the field path and the received value | pass | artifacts/L1/pytest.log · tests/test_validate_tenant_config.py |
| UT-03 | Tenant config: duplicate and dangling names | Test fixture | Duplicate group/policy names and references to unknown names | Fails naming the duplicate and the reference | pass | artifacts/L1/pytest.log · tests/test_validate_tenant_config.py |
| UT-04 | Tenant config: strict default | Test fixture | Omit `tenant_strict` | Evaluated as off | skip | reason: tenant_strict is playbook-level, not read by the value gate; covered by E2E-11 |
| UT-05 | Vault sort: ordering and comments | Test fixture | Sort an unsorted vault with comments | Keys alphabetical; comments and values preserved | pass | artifacts/L1/pytest.log · tests/test_sort_vault_keys.py |
| UT-06 | Vault sort: no-op path | Test fixture | Feed a file it cannot normalise | File returned byte-identical, exit 0 | skip | reason: no silent no-op path - an unnormalisable file is refused (exit 1, untouched), verified in tests/test_sort_vault_keys.py |
| UT-07 | Vault sort: content safety | Test fixture | Compare the line multiset before and after | Identical multiset; no line lost | pass | artifacts/L1/pytest.log · tests/test_sort_vault_keys.py |
| UT-08 | Inventory scaffold: idempotency | Temp directory | Run the scaffold twice with the same input | Second run leaves both files unchanged | pass | artifacts/L1/pytest.log · tests/test_ensure_inventory_host.py |
| UT-09 | Inventory scaffold: address override | Temp directory | Re-run with `FORCE_IP` and a new address | Address replaced; other settings kept | pass | artifacts/L1/pytest.log · tests/test_ensure_inventory_host.py |
| UT-10 | Inventory scaffold: port handling | Temp directory | Run with and without a port | Port written only when supplied | pass | artifacts/L1/pytest.log · tests/test_ensure_inventory_host.py |
| UT-11 | Template cleaning | Fixture with comments | Render the clean form | Comments gone, values and structure unchanged | pass | artifacts/L1/pytest.log · tests/test_render_clean_template.py |
| UT-12 | Knob audit: both directions | Temp tree | Remove and add keys on each side | One failure per difference | pass | artifacts/L1/pytest.log · tests/test_audit_example_knobs.py |
| UT-13 | Knob audit: whitelists | Temp tree | Add an internal and a derived knob | Neither reported as a missing example knob | pass | artifacts/L1/pytest.log · tests/test_audit_example_knobs.py |
| UT-14 | Host-key check: parsing | Fixture inventory output | Feed default and non-default ports | Both forms handled; malformed input rejected with exit code | skip | reason: check_host_keys.py is a lint guard, not a known_hosts parser; parsing lives in the Makefile target, covered by E2E-18..20 |
| UT-15 | Host-key check: changed key | Fixture | Change a key for one host | Reported as changed | skip | reason: same as UT-14 - changed-key detection is shell logic in hostkey-init, covered by E2E-19 |
| UT-16 | Retry wrapper: transient then success | Stub command | Fail twice, then succeed | Retries, returns success, logs attempts | pass | artifacts/L1/pytest.log · tests/test_shell_helpers.py |
| UT-17 | Retry wrapper: permanent error | Stub command | Fail with a non-transient error | Exits immediately with the same code | pass | artifacts/L1/pytest.log · tests/test_shell_helpers.py |
| UT-18 | Agent runner: no agent and refused key | Stub environment | Run without `SSH_AUTH_SOCK`, then with a refused key | Clear error without an agent; exactly one retry on refusal | pass | artifacts/L1/pytest.log · tests/test_shell_helpers.py |

## L2 — role

| ID | Case | Precondition | Action | Expected | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| RL-01 | Server render and settle | Disposable host, deployed | Re-run the `management` role | No change; containers healthy | todo | |
| RL-02 | Render is the source of truth | Deployed | Hand-edit `config.yaml` on the host, re-run | File restored to the rendered state | pass | artifacts/RL-02/ — tampered config restored on the next run |
| RL-03 | Dashboard and proxy wiring | Deployed | Inspect `dashboard.env` and the proxy labels | Dashboard reachable through the proxy; no secret in the rendered env file beyond the intended ones | todo | |
| RL-04 | Configurable TLS port | `exposed_port: 8443` | Deploy, inspect the compose file, `config.yaml` and the firewall contract | Published `8443:443`, advertised address uses 8443, firewall allows 8443 | todo | |
| RL-05 | Configurable stack directory | `stack_dir` set | Deploy, then restore | All rendered files, handlers and restore use that directory | todo | |
| RL-06 | Agent setup key source | Tenant applied | Run `make monitoring` | Key read from the host's own `vault_endpoint_setup_key`; peer joins | pass | artifacts/RL-10/ — agent joined using the host's own vault key |
| RL-07 | Agent without a key | No `vault_endpoint_setup_key` | Run `make monitoring` | Fails before starting the container, message names the variable and the fix | todo | |
| RL-08 | Agent peer groups | Setup key configured | Inspect the peer via the API | Peer in the groups the key assigns, no routes | pass | artifacts/CNV-05/ — peer in endpoint, no routes |
| RL-09 | Exporter listener | Monitoring enabled | `ss -lntp` and a probe from off-host | Bound to the overlay address only; nothing on public or loopback | pass | artifacts/SEC-08/ — 100.125.231.160:9100 only |
| RL-10 | CrowdSec units | Monitoring enabled | `systemctl status` for both units | Both active and enabled; bouncer loaded in nftables | pass | artifacts/RL-10/ — both units active and enabled |
| RL-11 | Log shipping | `alloy_enabled` with `loki_push_url` | Inspect containers and the central Loki | Alloy running; SSH journal events arrive | blocked | artifacts/RL-09/monitoring-1.log — central Loki unreachable from the rebuilt host |
| RL-12 | Firewall contract | Firewall enabled | Probe from the control node and an external host | Only 80/TCP, 443/TCP, 3478/UDP open; re-verification runs from the control node | pass | artifacts/RL-12/ — default drop, contract ports plus SSH and WireGuard only |
| RL-13 | Firewall idempotency | Firewall enabled | Re-run the role | No change; rule set identical | fail | artifacts/E2E-07/deploy-2.log — legacy-table drop reports changed every run (D-2) |
| RL-14 | Firewall unsafe precondition | Missing verified public address | Run the role | Refuses with an actionable message; rules unchanged | todo | |
| RL-15 | SSH hardening refuses to lock out | No keyed login available | Enable hardening | Refuses before writing the config | todo | |
| RL-16 | SSH hardening rollback | Keyed login available | Break verification (invalid directive), run | Config reverted; keyed login still works | todo | |
| RL-17 | Root login policy | Hardening enabled | Try each `sshd_permit_root_login` value | Effective config matches; keyed root login follows the policy | pass | artifacts/SEC-05/ — permitrootlogin no, keyed login works |
| RL-18 | Secret generation | Empty and pre-filled vault | Run the role twice, first with empty values | Missing values generated; non-empty values never rotated | pass | artifacts/E2E-07/ — secrets generated once, later runs left them unchanged |
| RL-19 | Vault handling | Generated secrets | Inspect the file and a verbose run | File always encrypted; no plaintext secret in output; tasks marked `no_log` | pass | artifacts/SEC-06/ — vault encrypted, no secret in -vvv output |

## L3 — end-to-end

| ID | Case | Precondition | Action | Expected | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| E2E-01 | Preflight: placeholder address | Inventory with the placeholder | `make dry-run` | Fails naming the placeholder and `make host-init` | pass | artifacts/E2E-01/ — placeholder rejected (message placeholders literal, D-6) |
| E2E-02 | Preflight: root login and toolchain | `ssh_user: root`; out-of-range ansible-core | `make dry-run` twice | Each fails with an actionable message and the override flag | pass | artifacts/E2E-02/ — out-of-range engine and root login both refused |
| E2E-03 | Bootstrap from scratch | Fresh host, root or keyed access | `make host-bootstrap HOST=<host>` | `iac` created, keyed, passwordless sudo; re-run leaves it unchanged | pass | artifacts/E2E-03/ — iac/admin created, keys authorized, Docker installed |
| E2E-04 | Deploy from scratch | Domain points at the host, ports reachable | `make deploy` | Server, dashboard and proxy up; tenant applied | pass | artifacts/E2E-07/deploy-3.log — completes after the D-1 fix; the first from-scratch run failed on D-1 |
| E2E-05 | External contract | Deployed | Probe 80/TCP, 443/TCP, 3478/UDP, certificate chain, dashboard, REST API, relay WebSocket | All reachable; certificate valid for `<test-domain>`; STUN responds | pass | artifacts/E2E-05/probes/external-after.txt — 80/443, TLS, dashboard 200, API 401, STUN |
| E2E-06 | Dry run on a fresh host | Nothing deployed | `make dry-run` | Completes without error | pass | artifacts/E2E-06/ — exit 0 on a fresh host |
| E2E-07 | Deploy idempotency | Deployed | `make deploy` again | No change outside the documented non-idempotent steps | fail | artifacts/E2E-07/deploy-2.log — two undocumented changes (D-2, D-4) |
| E2E-08 | Tenant plan | Token in vault | `make plan` | Read-only diff; no API write | pass | artifacts/E2E-08/plan.log — 0 changed, 26 unchanged |
| E2E-09 | Tenant apply | Token in vault | `make apply` | Groups, policies, networks, DNS and setup keys match the desired state | pass | artifacts/E2E-09/apply-1.log — exit 0 |
| E2E-10 | Tenant apply idempotency | Applied | `make apply` again | No change | pass | artifacts/E2E-08/plan.log — API diff 0 changed after apply |
| E2E-11 | Tenant strict mode | `tenant_strict` unset, then `true` | Apply with an unmanaged resource present | Unset leaves it alone; `true` removes it | skip | reason: strict mode deletes unmanaged API resources; not authorised in this run |
| E2E-12 | Tenant value gate | Invalid desired state | `make plan` | Fails before rendering or calling the API, one message per field | pass | artifacts/E2E-12/ — one local problem, no API call |
| E2E-13 | Tenant token rejected | Expired token | `make apply` | Stops with the dashboard recovery steps, no retry storm | pass | artifacts/E2E-13/ — 401 with the Dashboard recovery steps |
| E2E-14 | Setup key persistence | First apply | Inspect the vault, apply again | `vault_<setup-key-name>` written once, then preserved | pass | artifacts/E2E-09/ — keys persisted once, later runs leave the vault unchanged |
| E2E-15 | Owner bootstrap | No `owner_email`; then one set | Deploy each way | No token without an email; a usable token with one | skip | reason: the rebuilt host only exercised the owner_email path |
| E2E-16 | Backup | Deployed | `make backup` | Archive created and fetchable; container running afterwards | pass | artifacts/E2E-16/backup-2.log — 28 MB archive fetched, container running |
| E2E-17 | Restore | Archive and matching datastore key | `make restore FROM=...` | Data matches the snapshot; stack redeployed with the current key | pass | artifacts/E2E-17/ — restore exit 0, contract intact, plan 0 changed |
| E2E-18 | Host-key refresh | Reachable host | `make hostkey-init` | Known-hosts entry refreshed for every inventory host | pass | artifacts/E2E-18/hostkey-init-force.log — refreshed after operator confirmation |
| E2E-19 | Host-key change guard | Changed host key | `make hostkey-init`, then with `FORCE=1` | Refuses with the fingerprint and the flag; replaces only with the flag | pass | artifacts/E2E-18/key-compare.txt — changed key refused with fingerprint and FORCE hint |
| E2E-20 | Host-key atomicity | One unreachable host | `make hostkey-init` | Other hosts updated, failure reported, file not truncated or partially written | todo | |
| E2E-21 | Vault read and edit | Several hosts | `make vault-view`, `make vault-edit HOST=<host>` | Decrypts per host; edits stay encrypted and keys sorted | todo | |
| E2E-22 | Host scaffold | No host entry | `make host-init HOST=<host> HOST_IP=<address>` | Inventory, host vars and encrypted vault scaffolded; placeholder rejected until replaced | todo | |

## L4 — negative and destructive

| ID | Case | Precondition | Action | Expected | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| NEG-01 | Backup archive failure | Deployed | Force the archive step to fail | Container running again; error names the failed step | pass | artifacts/NEG-01/ — play fails, container restarted |
| NEG-02 | Restore with a corrupt archive | Deployed | Truncate the archive, restore | Fails at verification, stack still running, data untouched | pass | artifacts/NEG-02/ — fails before stopping, dashboard 200 |
| NEG-03 | Restore with a missing key | Archive without `vault_datastore_encryption_key` | Restore | Fails with the key recovery instructions before touching data | fail | artifacts/NEG-03/ — empty key regenerated silently, restored data unreadable (D-5) |
| NEG-04 | Restore without a source | Clean tree | `make restore` | Usage message, no host contacted | pass | artifacts/NEG-04/ — usage message, exit 2 |
| NEG-05 | Container killed | Monitoring and agent deployed | Kill the containers | Agent and exporters recover on their own | blocked | artifacts/NEG-05/ — docker kill leaves the stack down; PID 1 crash could not be forced |
| NEG-06 | Host reboot | Monitoring enabled | Reboot | Overlay bind succeeds after boot; no failed unit | skip | reason: a reboot needs a maintenance window |
| NEG-07 | Plaintext vault | A plaintext `vault.yml` | Run any vault-writing target | File encrypted again; no plaintext left behind | pass | artifacts/NEG-07/ — plaintext vault encrypted on write |
| NEG-08 | Missing vault | No `vault.yml` | Deploy | Fails with the scaffold or recovery instruction | skip | reason: would need a scratch host |
| NEG-09 | Transient API failure | Tenant applied | Inject a transient failure during apply | Retried within the limit, then success; a configuration error still fails fast | pass | artifacts/L1/pytest.log · tests/test_shell_helpers.py — covered by the retry wrapper unit tests |
| NEG-10 | Interrupted backup/restore | Deployed | Interrupt mid-run | Stack ends up running; no half-written archive is treated as valid | skip | reason: interruption is covered partly by NEG-01/NEG-02 |

## L5 — security

| ID | Case | Precondition | Action | Expected | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| SEC-01 | No secret in the tree | Clean tree | `git ls-files` and a targeted history scan | No vault, key or token; only the example templates | pass | artifacts/SEC-01/scan.txt — only the example vault template is tracked |
| SEC-02 | Host vars privacy | Clean tree | Inspect tracked paths under `inventory/host_vars` | Only `example/` tracked | pass | artifacts/SEC-01/ — only example/ tracked |
| SEC-03 | Vault at rest | Any host | Inspect the vault file | Encrypted; mode restricted; never plaintext on disk | pass | artifacts/E2E-04/defect/ — encrypted 0600, owner fixed by D-1 |
| SEC-04 | Sudo policy | Host bootstrapped | Inspect sudoers for both accounts | `iac` passwordless; `admin` password-protected; no stray entries | pass | artifacts/SEC-04/ — iac NOPASSWD, admin password sudo |
| SEC-05 | Effective SSH config | Hardening applied | `sshd -T` and a password-login attempt | Password login refused; keyed login works; matches the documented policy | pass | artifacts/SEC-05/ — password login off, keyed login survived |
| SEC-06 | Verbose output | Deployed | `-vvv` run of the secret-bearing playbooks | No plaintext secret in output | pass | artifacts/SEC-06/ — no vault value in -vvv output |
| SEC-07 | Container surface | Deployed | `docker inspect` ports, mounts, capabilities | Docker socket read-only; no unnecessary published ports or privileges | pass | artifacts/SEC-04/host-security-2.txt — docker socket read-only |
| SEC-08 | Exporter surface | Monitoring enabled | Scan local and public addresses | No listener outside the overlay | pass | artifacts/SEC-08/ — no listener outside the overlay |
| SEC-09 | File modes | Deployed | Inspect stack and monitoring directories | Directories `0700`, secret-bearing files `0600` | pass | artifacts/SEC-04/host-security-root.txt — 0755 dir, 0600 secret files |
| SEC-10 | Token expiry handling | Expired token | Tenant run | Fails fast with an actionable message; nothing rotated automatically | pass | artifacts/SEC-10/ — fails fast with recovery steps |

## L6 — convergence and contracts

| ID | Case | Precondition | Action | Expected | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| CNV-01 | Monitoring master switch off | Monitoring deployed | Set `monitoring_enabled: false`, run `make monitoring` | Node exporter and CrowdSec units stopped and disabled; Alloy stack removed; packages and rendered files kept | pass | artifacts/CNV-01/ — units stopped, packages kept |
| CNV-02 | Single component off | Monitoring deployed | Disable one component only | Only that component stops; the rest stay up | pass | artifacts/CNV-02/ — only node_exporter stopped |
| CNV-03 | Re-enable | Converged off | Enable again, run | Stack returns without reinstalling packages | pass | artifacts/CNV-03/ — back without reinstalling |
| CNV-04 | Absent unit | Package never installed | Converge that component off | Skipped without failing | pass | artifacts/CNV-01/ — absent Alloy stack skipped without failing |
| CNV-05 | Peer API contract | Server deployed | Query the peer list | `ip`, `dns_label` and `groups` present and stable across runs | pass | artifacts/CNV-05/ — ip, dns_label, groups present |
| CNV-06 | Setup-key to group mapping | Tenant applied | Inspect keys and peers | Keys assign the documented groups | pass | artifacts/CNV-06/ — three keys map to the documented groups |
| CNV-07 | Embedded DNS | Peers online | Resolve a peer name from inside the overlay | Resolves to the peer's overlay address | pass | artifacts/CNV-07/ — peer name resolves on the overlay |
| CNV-08 | Docs match behaviour | Clean tree | Compare `AGENTS.md`, `docs/components/` and `docs/RUNBOOK.md` with observed behaviour | No contradiction left unreported | pass | artifacts/E2E-01/, artifacts/NEG-03/ — contradictions recorded as D-5/D-6 |
