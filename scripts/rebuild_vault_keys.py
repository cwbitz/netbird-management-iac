#!/usr/bin/env python3
"""Print the vault keys of the host-returned NetBird secrets for one host.

The tenant state names the setup keys; the API returns each key's secret only at
creation time, and the tenant play stores it as ``vault_<name>`` with every
non-alphanumeric character replaced by ``_``. This helper derives exactly those
vault keys (plus the fixed ``admin`` service-user PAT) so ``REBUILD=1`` can prune
the values the previous server owned without touching anything else.

Usage: rebuild_vault_keys.py [tenant.yml]
Exit:  0 (always; a missing tenant file yields only the service PAT)
"""

from __future__ import annotations

import re
import sys

SERVICE_PAT = "vault_service_admin_access_token"
TOP_LEVEL = re.compile(r"^netbird_setup_keys\s*:\s*$")
NAME = re.compile(r"(?:^|-\s+|[{,]\s*)name\s*:\s*([^,}\n]+)")


def unquote(value):
    value = value.split(" #", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def setup_key_names(text):
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if TOP_LEVEL.match(line)), None)
    if start is None:
        return []
    names = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace() and not line.startswith("#"):
            break
        if line.lstrip().startswith("#"):
            continue
        match = NAME.search(line)
        if match:
            name = unquote(match.group(1))
            if name:
                names.append(name)
    return names


def vault_key(name):
    return "vault_" + re.sub(r"[^A-Za-z0-9_]", "_", name)


def main(argv):
    if len(argv) > 2:
        print("usage: rebuild_vault_keys.py [tenant.yml]", file=sys.stderr)
        return 2
    keys = [SERVICE_PAT]
    if len(argv) == 2:
        try:
            with open(argv[1], encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            print(f"warning: {argv[1]} not found; only the service PAT is pruned", file=sys.stderr)
        else:
            keys += [vault_key(name) for name in setup_key_names(text)]
    for key in dict.fromkeys(keys):
        print(key)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
