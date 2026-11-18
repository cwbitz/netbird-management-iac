#!/usr/bin/env python3
"""Remove a declared list of host-returned secrets from an encrypted vault.

`REBUILD=1` means the host was recreated, so secrets the previous host returned
(a service PAT, setup keys, API tokens) no longer exist there. The vault writers
preserve existing non-empty values, so a stale value would survive forever and
every later run would fail with it. This helper performs the explicit, opt-in
cleanup: it removes exactly the keys the caller declares, backs up the vault
first, and never prints a value.

Only top-level keys are considered. The write is refused when the vault changed
between the read and the write, encrypted atomically, and verified by decrypting
the result back. A plaintext vault is accepted and re-encrypted, matching the
vault writers.

Usage:
  prune_rebuild_secrets.py <vault.yml> [--key KEY]... [--keys-file FILE]
                            [--backup-dir DIR] [--dry-run]
                            [--ansible-vault PATH]

Exit: 0 pruned or nothing to prune, 1 refused, 2 usage.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from argparse import ArgumentParser
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sort_vault_keys import line_bag, sort_text, split_blocks  # noqa: E402

VAULT_MARKER = b"$ANSIBLE_VAULT"


def fingerprint(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def is_encrypted(path):
    with open(path, "rb") as handle:
        return VAULT_MARKER in handle.read(4096)


def decrypt(vault_bin, path):
    if not is_encrypted(path):
        with open(path, "rb") as handle:
            return 0, handle.read()
    result = subprocess.run([vault_bin, "view", path], capture_output=True)
    if result.returncode != 0:
        return result.returncode, result.stderr
    return 0, result.stdout


def encrypt(vault_bin, text, vault_path):
    directory = os.path.dirname(os.path.abspath(vault_path))
    handle, plain = tempfile.mkstemp(dir=directory, prefix=".vault-prune-", suffix=".yml")
    handle_out, encrypted = tempfile.mkstemp(dir=directory, prefix=".vault-", suffix=".tmp")
    os.close(handle_out)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(text)
        result = subprocess.run(
            [vault_bin, "encrypt", "--output", encrypted, plain], capture_output=True
        )
        if result.returncode != 0:
            return result.returncode, result.stderr.decode("utf-8", "replace").strip()
        if subprocess.run([vault_bin, "view", encrypted], capture_output=True).stdout.decode() != text:
            return 1, "the encrypted result did not decrypt back to the edited text"
        mode = os.stat(vault_path).st_mode & 0o777
        os.chmod(encrypted, mode)
        os.replace(encrypted, vault_path)
        return 0, ""
    finally:
        for leftover in (plain, encrypted):
            if os.path.exists(leftover):
                os.unlink(leftover)


def read_keys(path):
    keys = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.split("#", 1)[0].strip()
            if line:
                keys.append(line)
    return keys


def backup(path, backup_dir):
    os.makedirs(backup_dir, mode=0o700, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = os.path.join(backup_dir, f"vault-{stamp}.yml")
    suffix = 1
    while os.path.exists(target):
        target = os.path.join(backup_dir, f"vault-{stamp}-{suffix}.yml")
        suffix += 1
    shutil.copyfile(path, target)
    os.chmod(target, 0o600)
    return target


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("vault", help="encrypted vault file to prune")
    parser.add_argument("--key", action="append", default=[], help="top-level key to remove (repeatable)")
    parser.add_argument("--keys-file", help="file with one key per line (# comments allowed)")
    parser.add_argument("--backup-dir", help="directory for the encrypted vault backup")
    parser.add_argument("--dry-run", action="store_true", help="report what would be removed")
    parser.add_argument("--ansible-vault", help="ansible-vault binary (default: $ANSIBLE_VAULT_BIN or PATH)")
    args = parser.parse_args(argv)

    keys = list(args.key)
    if args.keys_file:
        keys += read_keys(args.keys_file)
    keys = list(dict.fromkeys(keys))
    if not keys:
        print("no host-returned secrets declared; nothing to prune")
        return 0

    path = os.path.abspath(args.vault)
    if not os.path.isfile(path):
        print(f"no vault at {path}; nothing to prune")
        return 0

    vault_bin = args.ansible_vault or os.environ.get("ANSIBLE_VAULT_BIN") or "ansible-vault"
    before = fingerprint(path)
    rc, original = decrypt(vault_bin, path)
    if rc != 0:
        print(f"could not decrypt {path}", file=sys.stderr)
        return rc

    try:
        original_text = original.decode("utf-8")
    except UnicodeDecodeError:
        print(f"{path} is not a UTF-8 vault", file=sys.stderr)
        return 1

    content = original_text if original_text.endswith("\n") else original_text + "\n"
    header, blocks = split_blocks(content)
    present = [key for key in keys if any(key == name for name, _ in blocks)]
    if not present:
        print(f"nothing to prune in {path}")
        return 0
    if args.dry_run:
        print("would prune: " + ", ".join(present))
        return 0
    if not args.backup_dir:
        print("--backup-dir is required unless --dry-run is used", file=sys.stderr)
        return 2
    if fingerprint(path) != before:
        print(f"refusing to prune {path}: it changed while being read", file=sys.stderr)
        return 1

    kept = [(name, block) for name, block in blocks if name not in present]
    pruned_text = "".join(header + [line for _, block in sorted(kept, key=lambda item: item[0]) for line in block])
    removed_text = "".join(line for name, block in blocks if name in present for line in block)
    if sorted(line_bag(pruned_text) + line_bag(removed_text)) != line_bag(content):
        print("refusing to prune: the remaining text does not round-trip", file=sys.stderr)
        return 1

    backup_path = backup(path, args.backup_dir)
    rc, detail = encrypt(vault_bin, pruned_text, path)
    if rc != 0:
        print(f"refusing to write the vault: encryption failed ({detail or 'no detail'})", file=sys.stderr)
        return 1
    print("pruned: " + ", ".join(present))
    print(f"backup: {backup_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
