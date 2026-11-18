"""Coverage for ``scripts/prune_rebuild_secrets.py``.

The tests use a fake ``ansible-vault`` (like ``test_edit_vault.py``), so no real
vault password or Ansible install is involved.
"""
from __future__ import annotations

import os
import stat

MARKER = "$ANSIBLE_VAULT;1.1;AES256\n"

FAKE_VAULT = """#!/bin/sh
cmd=$1; shift
case "$cmd" in
  view)
    sed '1d' "$1"
    ;;
  encrypt)
    out=$2; src=$3
    { printf '$ANSIBLE_VAULT;1.1;AES256\\n'; cat "$src"; } > "$out"
    ;;
  *)
    echo "unexpected ansible-vault command: $cmd" >&2
    exit 2
    ;;
esac
"""

VAULT_TEXT = (
    "---\n"
    'vault_alpha: "a"\n'
    'vault_service_admin_access_token: "stale-token-value"\n'
    'vault_zeta: "z"\n'
)


def make_executable(path):
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def setup(tmp_path, write_file, text=VAULT_TEXT, mode=0o600):
    vault_bin = make_executable(write_file("fake-ansible-vault", FAKE_VAULT))
    vault = write_file("vault.yml", MARKER + text, mode=mode)
    backup = tmp_path / "backup"
    return vault_bin, vault, backup


def test_prunes_the_declared_keys_sorts_and_backs_up(tmp_path, run_python, write_file):
    vault_bin, vault, backup = setup(tmp_path, write_file)

    result = run_python(
        "prune_rebuild_secrets.py",
        vault,
        "--ansible-vault",
        vault_bin,
        "--backup-dir",
        backup,
        "--key",
        "vault_service_admin_access_token",
    )

    assert result.returncode == 0, result.stderr
    assert "pruned: vault_service_admin_access_token" in result.stdout
    assert "stale-token-value" not in result.stdout + result.stderr
    content = vault.read_text()
    assert content.startswith(MARKER)
    assert content[len(MARKER):] == '---\nvault_alpha: "a"\nvault_zeta: "z"\n'
    assert os.stat(vault).st_mode & 0o777 == 0o600
    backups = sorted(backup.glob("vault-*.yml"))
    assert len(backups) == 1
    assert backups[0].read_text() == MARKER + VAULT_TEXT
    assert os.stat(backups[0]).st_mode & 0o777 == 0o600


def test_keys_file_with_comments(tmp_path, run_python, write_file):
    vault_bin, vault, backup = setup(
        tmp_path,
        write_file,
        text=(
            "---\n"
            'vault_alpha: "a"\n'
            'vault_first: "1"\n'
            'vault_second: "2"\n'
        ),
    )
    keys = write_file("keys.txt", "# host-returned\nvault_first\n\nvault_second  # setup key\n")

    result = run_python(
        "prune_rebuild_secrets.py",
        vault,
        "--ansible-vault",
        vault_bin,
        "--backup-dir",
        backup,
        "--keys-file",
        keys,
    )

    assert result.returncode == 0, result.stderr
    assert "pruned: vault_first, vault_second" in result.stdout
    assert 'vault_alpha: "a"' in vault.read_text()
    assert "vault_first" not in vault.read_text()
    assert "vault_second" not in vault.read_text()


def test_dry_run_changes_nothing(tmp_path, run_python, write_file):
    vault_bin, vault, backup = setup(tmp_path, write_file)
    before = vault.read_bytes()

    result = run_python(
        "prune_rebuild_secrets.py",
        vault,
        "--ansible-vault",
        vault_bin,
        "--backup-dir",
        backup,
        "--key",
        "vault_service_admin_access_token",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    assert "would prune: vault_service_admin_access_token" in result.stdout
    assert vault.read_bytes() == before
    assert not backup.exists()


def test_missing_keys_are_a_noop(tmp_path, run_python, write_file):
    vault_bin, vault, backup = setup(tmp_path, write_file)
    before = vault.read_bytes()

    result = run_python(
        "prune_rebuild_secrets.py",
        vault,
        "--ansible-vault",
        vault_bin,
        "--backup-dir",
        backup,
        "--key",
        "vault_not_there",
    )

    assert result.returncode == 0, result.stderr
    assert "nothing to prune" in result.stdout
    assert vault.read_bytes() == before
    assert not backup.exists()


def test_missing_vault_is_a_noop(tmp_path, run_python, write_file):
    vault_bin = make_executable(write_file("fake-ansible-vault", FAKE_VAULT))

    result = run_python(
        "prune_rebuild_secrets.py",
        tmp_path / "missing.yml",
        "--ansible-vault",
        vault_bin,
        "--backup-dir",
        tmp_path / "backup",
        "--key",
        "vault_alpha",
    )

    assert result.returncode == 0, result.stderr
    assert "no vault" in result.stdout


def test_no_declared_keys_is_a_noop(tmp_path, run_python, write_file):
    vault_bin, vault, backup = setup(tmp_path, write_file)
    before = vault.read_bytes()

    result = run_python(
        "prune_rebuild_secrets.py",
        vault,
        "--ansible-vault",
        vault_bin,
        "--backup-dir",
        backup,
    )

    assert result.returncode == 0, result.stderr
    assert "no host-returned secrets declared" in result.stdout
    assert vault.read_bytes() == before
    assert not backup.exists()


def test_requires_a_backup_dir_unless_dry_run(tmp_path, run_python, write_file):
    vault_bin, vault, _ = setup(tmp_path, write_file)
    before = vault.read_bytes()

    result = run_python(
        "prune_rebuild_secrets.py",
        vault,
        "--ansible-vault",
        vault_bin,
        "--key",
        "vault_service_admin_access_token",
    )

    assert result.returncode == 2
    assert "--backup-dir is required" in result.stderr
    assert vault.read_bytes() == before
