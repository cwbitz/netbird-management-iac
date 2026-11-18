"""Coverage for ``scripts/rebuild_vault_keys.py`` (NetBird host-returned keys)."""
from __future__ import annotations

import pathlib

SERVICE_PAT = "vault_service_admin_access_token"


def test_block_style_setup_keys(run_python, write_file):
    tenant = write_file(
        "tenant.yml",
        """---
tenant_strict: true
netbird_setup_keys:
  - name: "admin_setup_key"
    key_type: "reusable"
  - name: "endpoint-setup key"
    key_type: "reusable"
netbird_users: []
""",
    )

    result = run_python("rebuild_vault_keys.py", tenant)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        SERVICE_PAT,
        "vault_admin_setup_key",
        "vault_endpoint_setup_key",
    ]


def test_flow_style_setup_keys(run_python, write_file):
    tenant = write_file(
        "tenant.yml",
        """---
netbird_setup_keys:
  - { name: "admin_setup_key", key_type: "reusable" }
  - { name: "docker_host_setup_key", key_type: "reusable" }
""",
    )

    result = run_python("rebuild_vault_keys.py", tenant)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        SERVICE_PAT,
        "vault_admin_setup_key",
        "vault_docker_host_setup_key",
    ]


def test_comments_and_other_blocks_are_ignored(run_python, write_file):
    tenant = write_file(
        "tenant.yml",
        """---
# netbird_setup_keys:
#   - name: ignored
netbird_setup_keys:
  - name: "kept_setup_key"
netbird_users:
  - name: "owner"
    role: "owner"
""",
    )

    result = run_python("rebuild_vault_keys.py", tenant)

    assert result.returncode == 0, result.stderr
    assert "vault_kept_setup_key" in result.stdout
    assert "ignored" not in result.stdout
    assert "owner" not in result.stdout


def test_missing_tenant_file_yields_only_the_service_pat(run_python, tmp_path: pathlib.Path):
    result = run_python("rebuild_vault_keys.py", tmp_path / "missing.yml")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [SERVICE_PAT]
    assert "only the service PAT is pruned" in result.stderr


def test_non_alphanumerics_become_underscores(run_python, write_file):
    tenant = write_file(
        "tenant.yml",
        """---
netbird_setup_keys:
  - name: "home router/setup key"
""",
    )

    result = run_python("rebuild_vault_keys.py", tenant)

    assert result.returncode == 0, result.stderr
    assert "vault_home_router_setup_key" in result.stdout
