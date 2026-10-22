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
