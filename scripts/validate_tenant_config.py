#!/usr/bin/env python3
"""Validate the NetBird tenant desired state before it is rendered or applied.

``playbooks/tenant.yml`` dumps the effective tenant variables (after templating)
to JSON and runs this script before rendering the collection config, so
``make plan`` / ``make apply`` / the tenant step of ``make deploy`` fail fast —
before anything is rendered or applied — when a value is unusable.

Scope: shape and value only — types, enums, ranges, CIDR/domain/email syntax and
duplicate names. Cross-resource references that only the live account can settle
(peers, IdP-synced groups) stay the collection's preflight, not this gate.

Standard library only (like the other scripts/), so a plain `python3` can run it.

Usage: validate_tenant_config.py <vars.json>   # exit 1 with a report on failure
"""
from __future__ import annotations

import ipaddress
import json
import re
import sys

# --------------------------------------------------------------------------------
# Enumerations mirrored from the collection's module argument specs.
# --------------------------------------------------------------------------------
ACTIONS = {"accept", "drop"}
PROTOCOLS = {"all", "tcp", "udp", "icmp", "netbird-ssh"}
STATES = {"present", "absent"}
USER_ROLES = {"admin", "user", "owner", "network_admin", "auditor"}
KEY_TYPES = {"one-off", "reusable"}
NS_TYPES = {"udp", "tcp", "tls", "https"}
SERVICE_MODES = {"http", "tcp", "udp", "tls"}
TARGET_TYPES = {"subnet", "host", "domain", "peer", "cluster"}
RECORD_TYPES = {"A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV"}

# Account settings accepted by the collection's netbird_account module. The
# project's `*_expire_seconds` durations are mapped by playbooks/tenant.yml.
ALLOWED_SETTINGS = {
    "peer_login_expiration_enabled",
    "peer_login_expiration",
    "peer_login_expire_seconds",
    "peer_inactivity_expiration_enabled",
    "peer_inactivity_expiration",
    "peer_inactivity_expire_seconds",
    "regular_users_view_blocked",
    "groups_propagation_enabled",
    "jwt_groups_enabled",
    "jwt_groups_claim_name",
    "jwt_allow_groups",
    "routing_peer_dns_resolution_enabled",
    "dns_domain",
    "network_range",
    "network_range_v6",
    "ipv6_enabled_groups",
    "lazy_connection_enabled",
    "auto_update_always",
    "auto_update_version",
    "peer_expose_enabled",
    "peer_expose_groups",
    "extra_peer_approval_enabled",
    "extra_user_approval_required",
    "extra_network_traffic_logs_enabled",
    "extra_network_traffic_logs_groups",
    "extra_network_traffic_packet_counter_enabled",
}
BOOL_SETTINGS = {key for key in ALLOWED_SETTINGS if key.endswith(("_enabled", "_blocked", "_always"))}
INT_SETTINGS = {
    "peer_login_expiration",
    "peer_login_expire_seconds",
    "peer_inactivity_expiration",
    "peer_inactivity_expire_seconds",
}
LIST_SETTINGS = {
    "jwt_allow_groups",
    "ipv6_enabled_groups",
    "peer_expose_groups",
    "extra_network_traffic_logs_groups",
}

LABEL_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
VERSION_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PORT_RE = re.compile(r"^(\d+)(?:-(\d+))?$")


def is_text(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_domain(value) -> bool:
    """A DNS name (single label allowed, optional single leading wildcard)."""
    if not is_text(value) or len(value.rstrip(".")) > 253:
        return False
    text = value.rstrip(".").removeprefix("*.")
    return all(LABEL_RE.match(label) for label in text.split("."))


def is_network(value) -> bool:
    try:
        ipaddress.ip_network(str(value), strict=False)
        return True
    except ValueError:
        return False


def network_version(value) -> int | None:
    try:
        return ipaddress.ip_network(str(value), strict=False).version
    except ValueError:
        return None


def is_ip(value) -> bool:
    try:
        ipaddress.ip_address(str(value))
        return True
    except ValueError:
        return False


def is_port(value) -> bool:
    if isinstance(value, bool):
        return False
    match = PORT_RE.match(str(value).strip())
    if not match:
        return False
    start = int(match.group(1))
    end = int(match.group(2) or start)
    return 1 <= start <= end <= 65535


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.counts: dict[str, int] = {}

    def fail(self, path: str, message: str) -> None:
        self.problems.append(f"{path}: {message}")

    def sequence(self, state: dict, key: str) -> list:
        value = state.get(key, [])
        if value is None:
            self.fail(key, "must be a list (use [] for none)")
            return []
        if not isinstance(value, list):
            self.fail(key, f"must be a list, got {type(value).__name__}")
            return []
        self.counts[key] = len(value)
        return value

    def entry(self, key: str, index: int, item) -> dict | None:
        if not isinstance(item, dict):
            self.fail(f"{key}[{index}]", f"must be a mapping, got {type(item).__name__}")
            return None
        return item

    def name(self, key: str, index: int, item: dict, *, seen: set) -> str | None:
        name = item.get("name")
        path = f"{key}[{index}].name"
        if not is_text(name):
            self.fail(path, "required non-empty string")
            return None
        if name.lower() == "all":
            self.fail(path, "'All' is managed by NetBird and must not be declared")
        elif name in seen:
            self.fail(path, f"duplicate name '{name}'")
        seen.add(name)
        return name

    def state(self, key: str, index: int, item: dict) -> None:
        value = item.get("state", "present")
        if value not in STATES:
            self.fail(f"{key}[{index}].state", f"must be one of {sorted(STATES)}, got {value!r}")

    def names_list(self, path: str, value, *, allow_empty: bool = False) -> None:
        if not isinstance(value, list):
            self.fail(path, f"must be a list of group names, got {type(value).__name__}")
            return
        if not value and not allow_empty:
            self.fail(path, "must not be empty")
        for position, name in enumerate(value):
            if not is_text(name):
                self.fail(f"{path}[{position}]", "required non-empty group name")


def validate_settings(state: dict, report: Report) -> None:
    settings = state.get("netbird_settings", {})
    if settings is None:
        return
    if not isinstance(settings, dict):
        report.fail("netbird_settings", f"must be a mapping, got {type(settings).__name__}")
        return
    report.counts["netbird_settings"] = len(settings)
    for key, value in settings.items():
        path = f"netbird_settings.{key}"
        if key not in ALLOWED_SETTINGS:
            report.fail(path, "unknown setting (typo?); see inventory/host_vars/example/main.yml")
            continue
        if key in BOOL_SETTINGS:
            if not isinstance(value, bool):
                report.fail(path, f"must be true/false, got {value!r}")
        elif key in INT_SETTINGS:
            if not is_int(value) or value <= 0:
                report.fail(path, f"must be a positive integer (seconds), got {value!r}")
        elif key in LIST_SETTINGS:
            report.names_list(path, value, allow_empty=True)
        elif key == "network_range":
            if network_version(value) != 4:
                report.fail(path, f"must be an IPv4 CIDR, got {value!r}")
        elif key == "network_range_v6":
            if network_version(value) != 6:
                report.fail(path, f"must be an IPv6 CIDR, got {value!r}")
        elif key == "dns_domain":
            if not is_domain(value):
                report.fail(path, f"must be a DNS name, got {value!r}")
        elif key == "auto_update_version":
            if value not in ("disabled", "latest") and not VERSION_RE.match(str(value)):
                report.fail(path, f"must be 'disabled', 'latest' or a version, got {value!r}")
        elif key == "jwt_groups_claim_name":
            if not is_text(value):
                report.fail(path, "must be a non-empty string")


def validate_groups(state: dict, report: Report) -> None:
    seen: set = set()
    for index, item in enumerate(report.sequence(state, "netbird_groups")):
        item = report.entry("netbird_groups", index, item)
        if item is None:
            continue
        report.name("netbird_groups", index, item, seen=seen)
        report.state("netbird_groups", index, item)


def validate_policies(state: dict, report: Report) -> None:
    seen: set = set()
    for index, item in enumerate(report.sequence(state, "netbird_policies")):
        item = report.entry("netbird_policies", index, item)
        if item is None:
            continue
        report.name("netbird_policies", index, item, seen=seen)
        report.state("netbird_policies", index, item)
        if "enabled" in item and not isinstance(item["enabled"], bool):
            report.fail(f"netbird_policies[{index}].enabled", "must be true/false")
        checks = item.get("source_posture_checks", [])
        if checks:
            report.names_list(f"netbird_policies[{index}].source_posture_checks", checks)
        rules = item.get("rules")
        if rules is None:
            continue
        if not isinstance(rules, list) or not rules:
            report.fail(f"netbird_policies[{index}].rules", "must be a non-empty list")
            continue
        for rule_index, rule in enumerate(rules):
            rule = report.entry(f"netbird_policies[{index}].rules", rule_index, rule)
            if rule is None:
                continue
            path = f"netbird_policies[{index}].rules[{rule_index}]"
            if not is_text(rule.get("name")):
                report.fail(f"{path}.name", "required non-empty string")
            if "enabled" in rule and not isinstance(rule["enabled"], bool):
                report.fail(f"{path}.enabled", "must be true/false")
            report.names_list(f"{path}.sources", rule.get("sources"))
            report.names_list(f"{path}.destinations", rule.get("destinations"))
            protocol = rule.get("protocol", "all")
            if protocol not in PROTOCOLS:
                report.fail(f"{path}.protocol", f"must be one of {sorted(PROTOCOLS)}, got {protocol!r}")
            action = rule.get("action", "accept")
            if action not in ACTIONS:
                report.fail(f"{path}.action", f"must be one of {sorted(ACTIONS)}, got {action!r}")
            if "bidirectional" in rule and not isinstance(rule["bidirectional"], bool):
                report.fail(f"{path}.bidirectional", "must be true/false")
            ports = rule.get("ports")
            if ports is not None:
                if protocol not in ("tcp", "udp"):
                    report.fail(f"{path}.ports", f"only valid for tcp/udp, not {protocol!r}")
                if not isinstance(ports, list) or not ports:
                    report.fail(f"{path}.ports", "must be a non-empty list")
                else:
                    for port_index, port in enumerate(ports):
                        if not is_port(port):
                            report.fail(
                                f"{path}.ports[{port_index}]",
                                f"must be a port (1-65535) or start-end range, got {port!r}",
                            )


def validate_posture_checks(state: dict, report: Report) -> None:
    seen: set = set()
    for index, item in enumerate(report.sequence(state, "netbird_posture_checks")):
        item = report.entry("netbird_posture_checks", index, item)
        if item is None:
            continue
        report.name("netbird_posture_checks", index, item, seen=seen)
        report.state("netbird_posture_checks", index, item)
        checks = item.get("checks")
        if not isinstance(checks, dict) or not checks:
            report.fail(f"netbird_posture_checks[{index}].checks", "must be a non-empty mapping")


def validate_networks(state: dict, report: Report) -> None:
    seen: set = set()
    for index, item in enumerate(report.sequence(state, "netbird_networks")):
        item = report.entry("netbird_networks", index, item)
        if item is None:
            continue
        report.name("netbird_networks", index, item, seen=seen)
        report.state("netbird_networks", index, item)
        routers = item.get("routers")
        if not isinstance(routers, list) or not routers:
            report.fail(f"netbird_networks[{index}].routers", "must be a non-empty list")
        else:
            for router_index, router in enumerate(routers):
                path = f"netbird_networks[{index}].routers[{router_index}]"
                router = report.entry(f"netbird_networks[{index}].routers", router_index, router)
                if router is None:
                    continue
                if not is_text(router.get("peer")) and not router.get("peer_groups"):
                    report.fail(path, "requires 'peer' or 'peer_groups'")
                if "peer_groups" in router:
                    report.names_list(f"{path}.peer_groups", router["peer_groups"])
                if "metric" in router and (not is_int(router["metric"]) or router["metric"] < 0):
                    report.fail(f"{path}.metric", f"must be a non-negative integer, got {router['metric']!r}")
                for flag in ("masquerade", "enabled"):
                    if flag in router and not isinstance(router[flag], bool):
                        report.fail(f"{path}.{flag}", "must be true/false")
        resources = item.get("resources")
        if not isinstance(resources, list) or not resources:
            report.fail(f"netbird_networks[{index}].resources", "must be a non-empty list")
            continue
        resource_names: set = set()
        for resource_index, resource in enumerate(resources):
            path = f"netbird_networks[{index}].resources[{resource_index}]"
            resource = report.entry(f"netbird_networks[{index}].resources", resource_index, resource)
            if resource is None:
                continue
            name = resource.get("name")
            if not is_text(name):
                report.fail(f"{path}.name", "required non-empty string")
            elif name in resource_names:
                report.fail(f"{path}.name", f"duplicate resource name '{name}'")
            else:
                resource_names.add(name)
            address = resource.get("address")
            if not is_text(address):
                report.fail(f"{path}.address", "required CIDR or domain name")
            elif "/" in str(address):
                if not is_network(address):
                    report.fail(f"{path}.address", f"invalid CIDR '{address}'")
            elif not is_domain(address):
                report.fail(f"{path}.address", f"invalid domain '{address}'")
            report.names_list(f"{path}.groups", resource.get("groups"))
            if "enabled" in resource and not isinstance(resource["enabled"], bool):
                report.fail(f"{path}.enabled", "must be true/false")


def validate_dns(state: dict, report: Report) -> None:
    seen: set = set()
    for index, item in enumerate(report.sequence(state, "netbird_dns_nameserver_groups")):
        item = report.entry("netbird_dns_nameserver_groups", index, item)
        if item is None:
            continue
        report.name("netbird_dns_nameserver_groups", index, item, seen=seen)
        report.state("netbird_dns_nameserver_groups", index, item)
        nameservers = item.get("nameservers")
        if not isinstance(nameservers, list) or not nameservers:
            report.fail(f"netbird_dns_nameserver_groups[{index}].nameservers", "must be a non-empty list")
        else:
            for server_index, server in enumerate(nameservers):
                path = f"netbird_dns_nameserver_groups[{index}].nameservers[{server_index}]"
                server = report.entry(f"netbird_dns_nameserver_groups[{index}].nameservers", server_index, server)
                if server is None:
                    continue
                if not is_ip(server.get("ip")):
                    report.fail(f"{path}.ip", f"must be an IP address, got {server.get('ip')!r}")
                if server.get("ns_type", "udp") not in NS_TYPES:
                    report.fail(f"{path}.ns_type", f"must be one of {sorted(NS_TYPES)}")
                if "port" in server and (not is_int(server["port"]) or not 1 <= server["port"] <= 65535):
                    report.fail(f"{path}.port", f"must be 1-65535, got {server['port']!r}")
        report.names_list(f"netbird_dns_nameserver_groups[{index}].groups", item.get("groups"))
        domains = item.get("domains", [])
        if not isinstance(domains, list):
            report.fail(f"netbird_dns_nameserver_groups[{index}].domains", "must be a list")
        else:
            for domain_index, domain in enumerate(domains):
                if not is_domain(domain):
                    report.fail(
                        f"netbird_dns_nameserver_groups[{index}].domains[{domain_index}]",
                        f"invalid domain {domain!r}",
                    )
        for flag in ("enabled", "primary", "search_domains_enabled"):
            if flag in item and not isinstance(item[flag], bool):
                report.fail(f"netbird_dns_nameserver_groups[{index}].{flag}", "must be true/false")

    seen = set()
    for index, item in enumerate(report.sequence(state, "netbird_dns_zones")):
        item = report.entry("netbird_dns_zones", index, item)
        if item is None:
            continue
        report.name("netbird_dns_zones", index, item, seen=seen)
        report.state("netbird_dns_zones", index, item)
        if not is_domain(item.get("domain")):
            report.fail(f"netbird_dns_zones[{index}].domain", f"must be a DNS name, got {item.get('domain')!r}")
        report.names_list(f"netbird_dns_zones[{index}].distribution_groups", item.get("distribution_groups", []), allow_empty=True)
        records = item.get("records", [])
        if not isinstance(records, list):
            report.fail(f"netbird_dns_zones[{index}].records", "must be a list")
        else:
            for record_index, record in enumerate(records):
                path = f"netbird_dns_zones[{index}].records[{record_index}]"
                record = report.entry(f"netbird_dns_zones[{index}].records", record_index, record)
                if record is None:
                    continue
                if not is_text(record.get("name")):
                    report.fail(f"{path}.name", "required non-empty string")
                if record.get("type") not in RECORD_TYPES:
                    report.fail(f"{path}.type", f"must be one of {sorted(RECORD_TYPES)}")
                if record.get("content") is None:
                    report.fail(f"{path}.content", "required")
                if "ttl" in record and (not is_int(record["ttl"]) or record["ttl"] < 0):
                    report.fail(f"{path}.ttl", f"must be a non-negative integer, got {record['ttl']!r}")

    for index, name in enumerate(report.sequence(state, "netbird_dns_disabled_management_groups")):
        if not is_text(name):
            report.fail(f"netbird_dns_disabled_management_groups[{index}]", "required non-empty group name")


def validate_setup_keys(state: dict, report: Report) -> None:
    seen: set = set()
    for index, item in enumerate(report.sequence(state, "netbird_setup_keys")):
        item = report.entry("netbird_setup_keys", index, item)
        if item is None:
            continue
        report.name("netbird_setup_keys", index, item, seen=seen)
        report.state("netbird_setup_keys", index, item)
        if item.get("key_type", "one-off") not in KEY_TYPES:
            report.fail(f"netbird_setup_keys[{index}].key_type", f"must be one of {sorted(KEY_TYPES)}")
        expires = item.get("expires_in", 86400)
        if not is_int(expires) or not 1 <= expires <= 31536000:
            report.fail(f"netbird_setup_keys[{index}].expires_in", f"must be 1..31536000 seconds, got {expires!r}")
        usage_limit = item.get("usage_limit", 0)
        if not is_int(usage_limit) or usage_limit < 0:
            report.fail(f"netbird_setup_keys[{index}].usage_limit", f"must be >= 0, got {usage_limit!r}")
        if "ephemeral" in item and not isinstance(item["ephemeral"], bool):
            report.fail(f"netbird_setup_keys[{index}].ephemeral", "must be true/false")
        if "auto_groups" in item:
            report.names_list(f"netbird_setup_keys[{index}].auto_groups", item["auto_groups"], allow_empty=True)


def validate_services(state: dict, report: Report) -> None:
    seen: set = set()
    for index, item in enumerate(report.sequence(state, "netbird_services")):
        item = report.entry("netbird_services", index, item)
        if item is None:
            continue
        report.name("netbird_services", index, item, seen=seen)
        report.state("netbird_services", index, item)
        if not is_domain(item.get("domain")):
            report.fail(f"netbird_services[{index}].domain", f"must be a DNS name, got {item.get('domain')!r}")
        if item.get("mode", "http") not in SERVICE_MODES:
            report.fail(f"netbird_services[{index}].mode", f"must be one of {sorted(SERVICE_MODES)}")
        report.names_list(f"netbird_services[{index}].access_groups", item.get("access_groups", []), allow_empty=True)
        targets = item.get("targets", [])
        if not isinstance(targets, list):
            report.fail(f"netbird_services[{index}].targets", "must be a list")
        else:
            for target_index, target in enumerate(targets):
                path = f"netbird_services[{index}].targets[{target_index}]"
                target = report.entry(f"netbird_services[{index}].targets", target_index, target)
                if target is None:
                    continue
                if "port" in target and (not is_int(target["port"]) or not 1 <= target["port"] <= 65535):
                    report.fail(f"{path}.port", f"must be 1-65535, got {target['port']!r}")
                if "target_type" in target and target["target_type"] not in TARGET_TYPES:
                    report.fail(f"{path}.target_type", f"must be one of {sorted(TARGET_TYPES)}")

    seen = set()
    for index, item in enumerate(report.sequence(state, "netbird_service_domains")):
        item = report.entry("netbird_service_domains", index, item)
        if item is None:
            continue
        report.name("netbird_service_domains", index, item, seen=seen)
        report.state("netbird_service_domains", index, item)


def validate_users(state: dict, report: Report) -> None:
    seen: set = set()
    for index, item in enumerate(report.sequence(state, "netbird_users")):
        item = report.entry("netbird_users", index, item)
        if item is None:
            continue
        report.state("netbird_users", index, item)
        email = item.get("email")
        if item.get("state") == "absent":
            if not email and not is_text(item.get("id")):
                report.fail(f"netbird_users[{index}]", "state absent requires 'email' or 'id'")
        elif not is_text(email):
            report.fail(f"netbird_users[{index}].email", "required for a present user")
        elif not EMAIL_RE.match(str(email)):
            report.fail(f"netbird_users[{index}].email", f"invalid email {email!r}")
        elif email in seen:
            report.fail(f"netbird_users[{index}].email", f"duplicate user '{email}'")
        else:
            seen.add(email)
        if item.get("role", "user") not in USER_ROLES:
            report.fail(f"netbird_users[{index}].role", f"must be one of {sorted(USER_ROLES)}")
        if "auto_groups" in item:
            report.names_list(f"netbird_users[{index}].auto_groups", item["auto_groups"], allow_empty=True)

    seen = set()
    for index, item in enumerate(report.sequence(state, "netbird_service_users")):
        item = report.entry("netbird_service_users", index, item)
        if item is None:
            continue
        report.name("netbird_service_users", index, item, seen=seen)
        report.state("netbird_service_users", index, item)
        if item.get("role", "user") not in USER_ROLES:
            report.fail(f"netbird_service_users[{index}].role", f"must be one of {sorted(USER_ROLES)}")
        if "auto_groups" in item:
            report.names_list(f"netbird_service_users[{index}].auto_groups", item["auto_groups"], allow_empty=True)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: validate_tenant_config.py <vars.json>", file=sys.stderr)
        return 2
    try:
        with open(argv[1], encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        print(f"validate_tenant_config: cannot read {argv[1]}: {error}", file=sys.stderr)
        return 2
    if not isinstance(state, dict):
        print("validate_tenant_config: the input must be a JSON object", file=sys.stderr)
        return 2

    report = Report()
    validate_settings(state, report)
    validate_groups(state, report)
    validate_policies(state, report)
    validate_posture_checks(state, report)
    validate_networks(state, report)
    validate_dns(state, report)
    validate_setup_keys(state, report)
    validate_services(state, report)
    validate_users(state, report)

    if report.problems:
        print(f"tenant value gate: {len(report.problems)} problem(s):")
        for problem in report.problems:
            print(f"  - {problem}")
        return 1
    summary = ", ".join(f"{key}={count}" for key, count in report.counts.items() if count)
    print(f"tenant value gate: OK ({summary or 'empty desired state'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
