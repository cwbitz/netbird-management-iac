"""Coverage for ``scripts/ensure_inventory_host.py``."""
from __future__ import annotations

BASE = """---
management:
  hosts:
    existing:
      ansible_host: "192.0.2.10"
      ansible_port: 2222
"""

EMPTY_GROUP = """---
management:
  hosts:
"""


def test_adds_host_with_matching_indentation(run_python, write_file):
    inventory = write_file("hosts.yml", BASE)
    result = run_python("ensure_inventory_host.py", inventory, "new-host", "--ansible-host", "198.51.100.7")

    assert result.returncode == 0, result.stderr
    text = inventory.read_text()
    assert "    new-host:\n      ansible_host: \"198.51.100.7\"\n" in text
    assert 'existing:\n      ansible_host: "192.0.2.10"\n' in text
    assert text.startswith("---\nmanagement:\n  hosts:\n")


def test_second_run_is_idempotent(run_python, write_file):
    inventory = write_file("hosts.yml", BASE)
    run_python("ensure_inventory_host.py", inventory, "new-host", "--ansible-host", "198.51.100.7")
    first = inventory.read_text()

    result = run_python("ensure_inventory_host.py", inventory, "new-host", "--ansible-host", "198.51.100.7")
    assert result.returncode == 0
    assert "already present" in result.stdout
    assert inventory.read_text() == first


def test_conflicting_address_is_not_overwritten(run_python, write_file):
    inventory = write_file("hosts.yml", BASE)
    result = run_python("ensure_inventory_host.py", inventory, "existing", "--ansible-host", "203.0.113.5")

    assert result.returncode == 0
    assert "not changed" in result.stderr
    assert "FORCE_IP=1" in result.stderr
    assert "192.0.2.10" in inventory.read_text()


def test_force_overwrites_the_address(run_python, write_file):
    inventory = write_file("hosts.yml", BASE)
    result = run_python(
        "ensure_inventory_host.py", inventory, "existing", "--ansible-host", "203.0.113.5", "--force"
    )

    assert result.returncode == 0
    text = inventory.read_text()
    assert '203.0.113.5' in text
    assert "192.0.2.10" not in text
    assert "ansible_port: 2222" in text


def test_port_is_written_only_when_supplied(run_python, write_file):
    with_port = write_file("with-port.yml", BASE)
    run_python("ensure_inventory_host.py", with_port, "h", "--ansible-host", "198.51.100.1", "--ansible-port", "47616")
    assert "ansible_port: 47616" in with_port.read_text()

    without_port = write_file("without-port.yml", EMPTY_GROUP)
    run_python("ensure_inventory_host.py", without_port, "h", "--ansible-host", "198.51.100.1")
    text = without_port.read_text()
    assert "    h:\n      ansible_host: \"198.51.100.1\"\n" in text
    assert "ansible_port" not in text


def test_empty_group_gets_two_space_hosts_block(run_python, write_file):
    inventory = write_file("hosts.yml", EMPTY_GROUP)
    result = run_python("ensure_inventory_host.py", inventory, "h", "--ansible-host", "198.51.100.2")

    assert result.returncode == 0, result.stderr
    assert "    h:\n      ansible_host: \"198.51.100.2\"\n" in inventory.read_text()


def test_comment_is_appended(run_python, write_file):
    inventory = write_file("hosts.yml", BASE)
    run_python("ensure_inventory_host.py", inventory, "h", "--ansible-host", "198.51.100.3", "--comment", "test host")
    assert 'ansible_host: "198.51.100.3"  # test host' in inventory.read_text()


def test_missing_group_and_file_are_errors(run_python, write_file):
    inventory = write_file("hosts.yml", BASE)
    missing_group = run_python("ensure_inventory_host.py", inventory, "h", "--group", "nope")
    assert missing_group.returncode == 1
    assert "group 'nope' not found" in missing_group.stderr

    missing_file = run_python("ensure_inventory_host.py", inventory.parent / "absent.yml", "h")
    assert missing_file.returncode == 1
    assert "does not exist" in missing_file.stderr
