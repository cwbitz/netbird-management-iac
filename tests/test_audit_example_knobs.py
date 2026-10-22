"""Coverage for ``scripts/audit_example_knobs.py``.

Each case builds a minimal tree (example, schema, one role default), so the audit
is exercised without the real project files.
"""
from __future__ import annotations

import pathlib

EXAMPLE = """---
domain_name: "netbird.example.com"
acme_email: "admin@example.com"
owner_email: ""
owner_name: ""
allow_root_login: false
apt_mirror: ""
docker_registry_mirrors: []
tenant_strict: false
stack_dir: "/opt/netbird"
widget_mode: "on"
"""

KEYS = [
    "domain_name",
    "acme_email",
    "owner_email",
    "owner_name",
    "allow_root_login",
    "apt_mirror",
    "docker_registry_mirrors",
    "tenant_strict",
    "stack_dir",
    "widget_mode",
]


def build_tree(tmp_path: pathlib.Path, keys=None, example: str = EXAMPLE, defaults_extra: str = "") -> pathlib.Path:
    keys = KEYS if keys is None else keys
    root = tmp_path / "repo"
    (root / "inventory/host_vars/example").mkdir(parents=True)
    (root / "roles/demo/defaults").mkdir(parents=True)
    (root / "inventory/host_vars/example/main.yml").write_text(example, encoding="utf-8")
    schema = "operator_knob_schema:\n" + "".join(f"  {key}: \"is defined\"\n" for key in keys)
    (root / "inventory/knob_schema.yml").write_text(schema, encoding="utf-8")
    (root / "roles/demo/defaults/main.yml").write_text(
        '---\nwidget_mode: "on"\n' + defaults_extra, encoding="utf-8"
    )
    return root


def test_clean_tree_passes(run_python, tmp_path):
    root = build_tree(tmp_path)
    result = run_python("audit_example_knobs.py", root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_example_key_missing_from_schema_is_reported(run_python, tmp_path):
    root = build_tree(tmp_path, keys=[key for key in KEYS if key != "widget_mode"])
    result = run_python("audit_example_knobs.py", root)

    assert result.returncode == 1
    assert "widget_mode: present in the example but missing from inventory/knob_schema.yml" in result.stdout


def test_schema_key_missing_from_example_is_reported(run_python, tmp_path):
    root = build_tree(tmp_path, keys=KEYS + ["schema_only_knob"])
    result = run_python("audit_example_knobs.py", root)

    assert result.returncode == 1
    assert "schema_only_knob: in inventory/knob_schema.yml but not the example" in result.stdout


def test_default_drift_is_reported(run_python, tmp_path):
    root = build_tree(tmp_path)
    (root / "roles/demo/defaults/main.yml").write_text('---\nwidget_mode: "off"\n', encoding="utf-8")
    result = run_python("audit_example_knobs.py", root)

    assert result.returncode == 1
    assert "widget_mode: example value 'on' != effective default 'off'" in result.stdout


def test_derived_knob_must_be_absent_from_the_example(run_python, tmp_path):
    root = build_tree(
        tmp_path,
        example=EXAMPLE + 'netbird_peer_setup_key: "x"\n',
        keys=KEYS + ["netbird_peer_setup_key"],
        defaults_extra='netbird_peer_setup_key: "derived"\n',
    )
    result = run_python("audit_example_knobs.py", root)

    assert result.returncode == 1
    assert "must be omitted from the example" in result.stdout


def test_derived_knob_omitted_passes(run_python, tmp_path):
    root = build_tree(tmp_path, defaults_extra='netbird_peer_setup_key: "derived"\n')
    result = run_python("audit_example_knobs.py", root)

    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_example_is_an_error(run_python, tmp_path):
    result = run_python("audit_example_knobs.py", tmp_path / "empty")

    assert result.returncode == 1
    assert "does not exist" in result.stderr
