"""Shared fixtures for the control-node helper tests.

Every test runs the helper as a subprocess in a temporary directory, so the suite
never reads the real inventory, vault or backup tree.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _run(command: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    merged = dict(os.environ)
    merged.pop("SSH_AGENT_ENV", None)
    if env:
        merged.update(env)
    return subprocess.run(command, capture_output=True, text=True, env=merged, timeout=60)


@pytest.fixture
def run_python():
    def run(name: str, *args: object, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return _run([sys.executable, str(SCRIPTS / name), *map(str, args)], env=env)

    return run


@pytest.fixture
def run_shell():
    def run(name: str, *args: object, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return _run(["bash", str(SCRIPTS / name), *map(str, args)], env=env)

    return run


@pytest.fixture
def write_file(tmp_path):
    def write(name: str, content: str, mode: int | None = None) -> pathlib.Path:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if mode is not None:
            path.chmod(mode)
        return path

    return write
