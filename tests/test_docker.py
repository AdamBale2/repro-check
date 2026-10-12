"""End-to-end tests against a real Docker daemon. Skipped when Docker is not available."""

import shutil
import subprocess
from pathlib import Path

import pytest

from repro_check.runner import Outcome, Runner, main_target, release_target

pytestmark = pytest.mark.docker

DEMO_PROJECT = Path(__file__).parent / "fixtures" / "demo_project"


def _docker_works() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


if not _docker_works():
    pytest.skip("Docker is not available", allow_module_level=True)


def test_main_target_runs_the_example():
    runner = Runner(timeout=60)
    target = main_target(DEMO_PROJECT, "3.12")
    assert runner.run(target, "import demo\nassert demo.add(2, 2) == 4\n").outcome is Outcome.PASSED
    failing = runner.run(target, "import demo\nassert demo.add(2, 2) == 5\n")
    assert failing.outcome is Outcome.FAILED
    assert "AssertionError" in failing.output


def test_release_target_from_pypi():
    result = Runner().run(release_target("six", "3.12"), "import six\nassert six.PY3\n")
    assert result.outcome is Outcome.PASSED


def test_sandbox_has_no_network():
    snippet = "import socket\nsocket.create_connection(('pypi.org', 443), timeout=5)\n"
    result = Runner().run(release_target("six", "3.12"), snippet)
    assert result.outcome is Outcome.FAILED


def test_sandbox_is_read_only_outside_tmp():
    result = Runner().run(release_target("six", "3.12"), "open('/usr/evil', 'w')\n")
    assert result.outcome is Outcome.FAILED


def test_tmp_is_writable_by_the_unprivileged_user():
    snippet = "import os\nassert os.getuid() == 65534\nopen('/tmp/ok', 'w').write('x')\n"
    result = Runner().run(release_target("six", "3.12"), snippet)
    assert result.outcome is Outcome.PASSED, result.output


def test_traceback_starts_at_the_example():
    result = Runner().run(release_target("six", "3.12"), "raise ValueError('boom')\n")
    assert result.outcome is Outcome.FAILED
    assert "harness" not in result.output
    assert 'File "/repro/repro.py", line 1' in result.output


def test_infinite_loop_times_out():
    result = Runner(timeout=5).run(release_target("six", "3.12"), "while True:\n    pass\n")
    assert result.outcome is Outcome.TIMED_OUT


def test_syntax_error_is_reported():
    result = Runner().run(release_target("six", "3.12"), "def broken(:\n")
    assert result.outcome is Outcome.INVALID_EXAMPLE
