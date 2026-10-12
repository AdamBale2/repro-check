from __future__ import annotations

import pytest

from repro_check.runner import CommandResult, CommandTimeout


class FakeDocker:
    """Stands in for the docker CLI: records commands and replays scripted results."""

    def __init__(self, run_results=None, build_fails=()):
        # One entry per `docker run`, in order: an exit code, or "timeout".
        self.run_results = list(run_results or [])
        self.build_fails = set(build_fails)
        self.calls: list[list[str]] = []
        self.snippets: list[str] = []

    def __call__(self, args, timeout):
        self.calls.append(list(args))
        command = args[1]
        if command == "build":
            dockerfile = args[args.index("-f") + 1]
            key = dockerfile.rsplit(".", 1)[-1]
            if key in self.build_fails:
                return CommandResult(1, f"ERROR: could not install ({key})")
            return CommandResult(0, "built")
        if command == "run":
            mount = args[args.index("-v") + 1]
            repro_dir = mount.split(":")[0]
            with open(f"{repro_dir}/repro.py", encoding="utf-8") as f:
                self.snippets.append(f.read())
            result = self.run_results.pop(0)
            if result == "timeout":
                raise CommandTimeout("still running...")
            return CommandResult(result, "Traceback ...\nAssertionError" if result else "ok")
        if command == "rm":
            return CommandResult(0, "")
        raise AssertionError(f"unexpected command: {args}")


@pytest.fixture
def fake_docker():
    return FakeDocker
