"""Coverage for ``scripts/retry-transient.sh``."""
from __future__ import annotations

import pathlib
import stat


def make_script(tmp_path: pathlib.Path, name: str, body: str) -> pathlib.Path:
    path = tmp_path / name
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_transient_failure_is_retried(run_shell, tmp_path):
    counter = tmp_path / "count"
    counter.write_text("0", encoding="utf-8")
    command = make_script(
        tmp_path,
        "flaky.sh",
        f"""n=$(cat {counter}); n=$((n+1)); echo $n > {counter}
if [ "$n" -lt 3 ]; then echo "Connection reset by peer" >&2; exit 5; fi
echo "ok on attempt $n"
""",
    )
    result = run_shell(
        "retry-transient.sh", command, env={"RETRY_MAX": "5", "RETRY_DELAY": "0"}
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ok on attempt 3" in result.stdout
    assert result.stderr.count("retrying") == 2



def test_permanent_failure_is_not_retried(run_shell, tmp_path):
    command = make_script(tmp_path, "broken.sh", 'echo "invalid token" >&2; exit 17\n')
    result = run_shell(
        "retry-transient.sh", command, env={"RETRY_MAX": "3", "RETRY_DELAY": "0"}
    )

    assert result.returncode == 17
    assert "not a transient network failure" in result.stderr
    assert ">>> transient network failure" not in result.stderr



def test_retry_limit_is_reported(run_shell, tmp_path):
    counter = tmp_path / "count"
    counter.write_text("0", encoding="utf-8")
    command = make_script(
        tmp_path,
        "always-flaky.sh",
        f"""n=$(cat {counter}); n=$((n+1)); echo $n > {counter}
echo "Connection refused" >&2; exit 9
""",
    )
    result = run_shell(
        "retry-transient.sh", command, env={"RETRY_MAX": "2", "RETRY_DELAY": "0"}
    )

    assert result.returncode == 9
    assert "giving up after 2 attempt" in result.stderr
    assert counter.read_text().strip() == "2"


