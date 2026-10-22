"""Value-gate coverage for ``scripts/validate_tenant_config.py``."""
from __future__ import annotations

import json

import pytest


def gate(run_python, tmp_path, state, name="state.json"):
    path = tmp_path / name
    path.write_text(json.dumps(state), encoding="utf-8")
    return run_python("validate_tenant_config.py", path)


def assert_fails(result, *fragments):
    assert result.returncode == 1, result.stdout + result.stderr
    for fragment in fragments:
        assert fragment in result.stdout, result.stdout


def test_empty_state_is_valid(run_python, tmp_path):
    result = gate(run_python, tmp_path, {})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "empty desired state" in result.stdout


def test_minimal_valid_state(run_python, tmp_path):
    state = {
        "netbird_settings": {"dns_domain": "netbird.example.com", "network_range": "100.64.0.0/10"},
        "netbird_groups": [{"name": "home-router"}, {"name": "endpoint", "state": "present"}],
        "netbird_setup_keys": [{"name": "endpoint_setup_key", "auto_groups": ["endpoint"]}],
    }
    result = gate(run_python, tmp_path, state)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "netbird_groups=2" in result.stdout


@pytest.mark.parametrize(
    ("settings", "fragment"),
    [
        ({"no_such_setting": True}, "unknown setting"),
        ({"peer_login_expiration_enabled": "yes"}, "must be true/false"),
        ({"peer_login_expiration": 0}, "positive integer"),
        ({"peer_login_expiration": True}, "positive integer"),
        ({"network_range": "fd00::/64"}, "IPv4 CIDR"),
        ({"network_range_v6": "100.64.0.0/10"}, "IPv6 CIDR"),
        ({"dns_domain": "-bad.example"}, "DNS name"),
        ({"auto_update_version": "newest"}, "'disabled', 'latest'"),
        ({"jwt_groups_claim_name": "   "}, "non-empty string"),
        ({"jwt_allow_groups": "admins"}, "must be a list"),
    ],
)
def test_settings_rejections(run_python, tmp_path, settings, fragment):
    assert_fails(gate(run_python, tmp_path, {"netbird_settings": settings}), fragment)


def test_settings_must_be_a_mapping(run_python, tmp_path):
    assert_fails(gate(run_python, tmp_path, {"netbird_settings": []}), "must be a mapping")


def test_groups_reject_all_and_duplicates(run_python, tmp_path):
    result = gate(
        run_python,
        tmp_path,
        {"netbird_groups": [{"name": "All"}, {"name": "dup"}, {"name": "dup"}, {"name": ""}]},
    )
    assert_fails(result, "'All' is managed", "duplicate name 'dup'", "required non-empty string")


def test_sequence_must_be_a_list(run_python, tmp_path):
    assert_fails(gate(run_python, tmp_path, {"netbird_groups": {"name": "x"}}), "must be a list")


def test_policy_rule_rejections(run_python, tmp_path):
    state = {
        "netbird_policies": [
            {
                "name": "policy",
                "rules": [
                    {
                        "name": "rule",
                        "sources": ["a"],
                        "destinations": ["b"],
                        "protocol": "all",
                        "ports": ["80"],
                        "action": "permit",
                    }
                ],
            }
        ]
    }
    assert_fails(gate(run_python, tmp_path, state), "only valid for tcp/udp", "must be one of")


def test_policy_port_range_is_bounded(run_python, tmp_path):
    state = {
        "netbird_policies": [
            {
                "name": "policy",
                "rules": [
                    {
                        "name": "rule",
                        "sources": ["a"],
                        "destinations": ["b"],
                        "protocol": "tcp",
                        "ports": ["80", "70000-80000", "900-100"],
                    }
                ],
            }
        ]
    }
    result = gate(run_python, tmp_path, state)
    assert_fails(result, "ports[1]", "ports[2]")


def test_policy_requires_rules(run_python, tmp_path):
    assert_fails(gate(run_python, tmp_path, {"netbird_policies": [{"name": "p", "rules": []}]}), "non-empty list")


def test_network_rejections(run_python, tmp_path):
    state = {
        "netbird_networks": [
            {
                "name": "lan",
                "routers": [{"peer": ""}],
                "resources": [
                    {"name": "r", "address": "10.0.0.0/33", "groups": ["g"]},
                    {"name": "r", "address": "bad_domain!", "groups": []},
                ],
            }
        ]
    }
    assert_fails(gate(run_python, tmp_path, state), "requires 'peer'", "invalid CIDR", "duplicate resource name", "must not be empty")


def test_network_requires_routers_and_resources(run_python, tmp_path):
    state = {"netbird_networks": [{"name": "lan", "routers": [], "resources": []}]}
    assert_fails(gate(run_python, tmp_path, state), "routers", "resources")


def test_dns_rejections(run_python, tmp_path):
    state = {
        "netbird_dns_nameserver_groups": [
            {
                "name": "ns",
                "nameservers": [{"ip": "not-an-ip", "ns_type": "doh", "port": 0}],
                "groups": ["g"],
                "domains": ["bad_domain!"],
            }
        ],
        "netbird_dns_zones": [
            {"name": "zone", "domain": "-bad", "records": [{"name": "a", "type": "ALIAS", "content": None}]}
        ],
    }
    assert_fails(gate(run_python, tmp_path, state), "must be an IP address", "must be one of", "1-65535", "invalid domain", "required")


def test_setup_key_rejections(run_python, tmp_path):
    state = {
        "netbird_setup_keys": [
            {"name": "k", "key_type": "forever", "expires_in": 0, "usage_limit": -1}
        ]
    }
    assert_fails(gate(run_python, tmp_path, state), "must be one of", "1..31536000", "must be >= 0")


def test_service_rejections(run_python, tmp_path):
    state = {
        "netbird_services": [
            {"name": "svc", "domain": "bad_domain!", "mode": "smtp", "targets": [{"port": 0}]}
        ]
    }
    assert_fails(gate(run_python, tmp_path, state), "must be a DNS name", "must be one of", "1-65535")


def test_user_rejections(run_python, tmp_path):
    state = {
        "netbird_users": [
            {"email": "nope", "role": "admin"},
            {"email": "dup@example.com", "role": "operator"},
            {"email": "dup@example.com", "role": "user", "auto_groups": "g"},
        ]
    }
    assert_fails(gate(run_python, tmp_path, state), "invalid email", "must be one of", "duplicate user", "must be a list")


def test_absent_entry_needs_identity(run_python, tmp_path):
    assert_fails(
        gate(run_python, tmp_path, {"netbird_users": [{"state": "absent", "role": "user"}]}),
        "state absent requires",
    )


def test_unreadable_and_malformed_input(run_python, tmp_path):
    assert run_python("validate_tenant_config.py", tmp_path / "missing.json").returncode == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = run_python("validate_tenant_config.py", bad)
    assert result.returncode == 2
    assert "cannot read" in result.stderr


def test_non_object_input_is_rejected(run_python, tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[]", encoding="utf-8")
    result = run_python("validate_tenant_config.py", path)
    assert result.returncode == 2
    assert "must be a JSON object" in result.stderr


def test_usage_without_arguments(run_python):
    result = run_python("validate_tenant_config.py")
    assert result.returncode == 2
    assert "Usage:" in result.stderr
