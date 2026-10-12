"""Build an image per target and run the example inside it, isolated."""

from __future__ import annotations

import contextlib
import re
import shlex
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

# Exit code the harness uses when the example is not valid Python.
INVALID_EXAMPLE_EXIT = 97
# Exit codes reserved by `docker run` for its own errors.
DOCKER_ERROR_EXITS = {125, 126, 127}

OUTPUT_TAIL_BYTES = 64_000
BUILD_TIMEOUT_SECONDS = 900

HARNESS = f"""\
import runpy
import sys
import traceback

path = "/repro/repro.py"
with open(path, encoding="utf-8") as f:
    source = f.read()
try:
    compile(source, path, "exec")
except SyntaxError as exc:
    print(f"The example is not valid Python: {{exc}}", file=sys.stderr)
    sys.exit({INVALID_EXAMPLE_EXIT})
try:
    runpy.run_path(path, run_name="__main__")
except SystemExit:
    raise
except BaseException as exc:
    # Show the traceback from the example onwards, without the harness frames.
    tb = exc.__traceback__
    while tb is not None and tb.tb_frame.f_code.co_filename != path:
        tb = tb.tb_next
    traceback.print_exception(type(exc), exc, tb or exc.__traceback__)
    sys.exit(1)
"""

_PYTHON_VERSION = re.compile(r"^\d+\.\d+(\.\d+)?$")


class Outcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    TIMED_OUT = "timed-out"
    INVALID_EXAMPLE = "invalid-example"
    SETUP_ERROR = "setup-error"

    @property
    def conclusive(self) -> bool:
        return self in (Outcome.PASSED, Outcome.FAILED)


@dataclass(frozen=True)
class Target:
    key: str  # "release" or "main"
    label: str  # shown in the report
    dockerfile: str
    context: Path | None  # build context; None means an empty one


@dataclass(frozen=True)
class RunResult:
    target: Target
    outcome: Outcome
    exit_code: int | None
    duration: float
    output: str


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    output: str


class CommandTimeout(Exception):
    def __init__(self, output: str):
        super().__init__("command timed out")
        self.output = output


class Executor(Protocol):
    def __call__(self, args: list[str], timeout: float) -> CommandResult: ...


def run_command(args: list[str], timeout: float) -> CommandResult:
    """Run a command, keeping only the tail of its output so memory stays bounded."""
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    tail = bytearray()

    def read() -> None:
        assert proc.stdout is not None
        while chunk := proc.stdout.read1(65536):
            tail.extend(chunk)
            if len(tail) > 2 * OUTPUT_TAIL_BYTES:
                del tail[:-OUTPUT_TAIL_BYTES]

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        reader.join(timeout=5)
        raise CommandTimeout(_decode(tail)) from None
    reader.join(timeout=5)
    return CommandResult(returncode, _decode(tail))


def _decode(data: bytes | bytearray) -> str:
    return bytes(data[-OUTPUT_TAIL_BYTES:]).decode("utf-8", errors="replace")


def check_python_version(version: str) -> str:
    if not _PYTHON_VERSION.match(version):
        raise ValueError(f"invalid python-version: {version!r} (expected e.g. 3.12)")
    return version


def release_target(package: str, python_version: str) -> Target:
    """The latest release, installed from the package index."""
    if not package.strip() or "\n" in package or "\r" in package:
        raise ValueError(f"invalid package requirement: {package!r}")
    spec = shlex.quote(package.strip())
    dockerfile = (
        f"FROM python:{check_python_version(python_version)}-slim\n"
        f"RUN pip install --no-cache-dir --disable-pip-version-check {spec}\n"
    )
    return Target("release", f"Latest release (`{package.strip()}`)", dockerfile, None)


def main_target(source: Path, python_version: str) -> Target:
    """The checked-out source tree, usually the default branch.

    The source is turned into a wheel in a first stage, so the final image does not
    contain the repository or its .git directory.
    """
    version = check_python_version(python_version)
    dockerfile = (
        f"FROM python:{version}-slim AS build\n"
        "RUN apt-get update && apt-get install -y --no-install-recommends git"
        " && rm -rf /var/lib/apt/lists/*\n"
        "COPY . /src\n"
        "RUN git config --global --add safe.directory '*'"
        " && pip wheel --no-cache-dir --disable-pip-version-check --no-deps"
        " --wheel-dir /wheels /src\n"
        f"FROM python:{version}-slim\n"
        "COPY --from=build /wheels /wheels\n"
        "RUN pip install --no-cache-dir --disable-pip-version-check /wheels/*.whl"
        " && rm -rf /wheels\n"
    )
    return Target("main", "Default branch", dockerfile, source)


def docker_run_args(image: str, name: str, repro_dir: Path) -> list[str]:
    """`docker run` arguments: no network, no secrets, read-only, capped resources."""
    return [
        "docker", "run", "--rm",
        "--name", name,
        "--network", "none",
        "--read-only",
        "--tmpfs", "/tmp:rw,size=64m,mode=1777",
        "--memory", "512m",
        "--memory-swap", "512m",
        "--cpus", "1",
        "--pids-limit", "128",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", "65534:65534",
        "-e", "HOME=/tmp",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "PYTHONUNBUFFERED=1",
        "-v", f"{repro_dir}:/repro:ro",
        "-w", "/tmp",
        image,
        "python", "/repro/harness.py",
    ]  # fmt: skip


class Runner:
    def __init__(self, executor: Executor = run_command, timeout: float = 60):
        self.executor = executor
        self.timeout = timeout

    def build(self, target: Target, workdir: Path) -> tuple[str | None, str]:
        """Build the target's image. Returns (tag, output); tag is None on failure."""
        tag = f"repro-check-{target.key}:{uuid.uuid4().hex[:12]}"
        dockerfile = workdir / f"Dockerfile.{target.key}"
        dockerfile.write_text(target.dockerfile, encoding="utf-8")
        context = target.context
        if context is None:
            context = workdir / f"empty-context-{target.key}"
            context.mkdir(exist_ok=True)
        args = ["docker", "build", "-t", tag, "-f", str(dockerfile), str(context)]
        try:
            result = self.executor(args, BUILD_TIMEOUT_SECONDS)
        except CommandTimeout as exc:
            return None, exc.output + "\n[build timed out]"
        if result.returncode != 0:
            return None, result.output
        return tag, result.output

    def run(self, target: Target, snippet: str) -> RunResult:
        with tempfile.TemporaryDirectory(prefix="repro-check-") as tmp:
            workdir = Path(tmp)
            start = time.monotonic()
            image, build_output = self.build(target, workdir)
            if image is None:
                return RunResult(
                    target, Outcome.SETUP_ERROR, None, time.monotonic() - start, build_output
                )

            repro_dir = workdir / "repro"
            repro_dir.mkdir()
            (repro_dir / "repro.py").write_text(snippet, encoding="utf-8")
            (repro_dir / "harness.py").write_text(HARNESS, encoding="utf-8")
            # The container runs as an unprivileged user that must be able to read these.
            repro_dir.chmod(0o755)
            for f in repro_dir.iterdir():
                f.chmod(0o644)

            name = f"repro-check-{uuid.uuid4().hex[:12]}"
            start = time.monotonic()
            try:
                result = self.executor(docker_run_args(image, name, repro_dir), self.timeout)
            except CommandTimeout as exc:
                self._force_remove(name)
                return RunResult(
                    target, Outcome.TIMED_OUT, None, time.monotonic() - start, exc.output
                )
            duration = time.monotonic() - start
            return RunResult(
                target, _outcome(result.returncode), result.returncode, duration, result.output
            )

    def _force_remove(self, name: str) -> None:
        with contextlib.suppress(CommandTimeout):
            self.executor(["docker", "rm", "-f", name], 30)


def _outcome(returncode: int) -> Outcome:
    if returncode == 0:
        return Outcome.PASSED
    if returncode == INVALID_EXAMPLE_EXIT:
        return Outcome.INVALID_EXAMPLE
    if returncode in DOCKER_ERROR_EXITS:
        return Outcome.SETUP_ERROR
    return Outcome.FAILED
