import shlex
from pathlib import Path

import pytest

from repro_check.runner import (
    INVALID_EXAMPLE_EXIT,
    Outcome,
    Runner,
    docker_run_args,
    main_target,
    release_target,
)


def test_release_dockerfile_quotes_requirement():
    requirement = "demo>=1.0; python_version>'3'"
    target = release_target(requirement, "3.12")
    from_line, run_line = target.dockerfile.splitlines()
    assert from_line == "FROM python:3.12-slim"
    # The shell sees the requirement as one single argument.
    assert shlex.split(run_line.removeprefix("RUN "))[-1] == requirement


@pytest.mark.parametrize("bad", ["", "  ", "demo\nRUN curl evil", "demo\r"])
def test_release_rejects_bad_requirement(bad):
    with pytest.raises(ValueError):
        release_target(bad, "3.12")


@pytest.mark.parametrize("bad", ["3", "latest", "3.12-slim", "3.12\nRUN x", ""])
def test_rejects_bad_python_version(bad):
    with pytest.raises(ValueError):
        release_target("demo", bad)


def test_main_image_does_not_keep_the_source(tmp_path):
    target = main_target(tmp_path, "3.11")
    final_stage = target.dockerfile.split("FROM python:3.11-slim\n", 1)[1]
    assert "COPY --from=build /wheels /wheels" in final_stage
    assert "/src" not in final_stage


def test_container_is_isolated():
    args = docker_run_args("img", "name", Path("/tmp/x"))
    joined = " ".join(args)
    for expected in (
        "--network none",
        "--read-only",
        "--tmpfs /tmp:rw,size=64m,mode=1777",
        "--cap-drop ALL",
        "--security-opt no-new-privileges",
        "--user 65534:65534",
        "--pids-limit 128",
        "--memory 512m",
        "-v /tmp/x:/repro:ro",
    ):
        assert expected in joined
    # Only the variables we set explicitly: nothing from the host, so no token.
    env_values = [args[i + 1] for i, a in enumerate(args) if a == "-e"]
    assert all(not v.startswith(("GITHUB", "REPRO_CHECK")) for v in env_values)


@pytest.mark.parametrize(
    ("exit_code", "outcome"),
    [
        (0, Outcome.PASSED),
        (1, Outcome.FAILED),
        (137, Outcome.FAILED),
        (INVALID_EXAMPLE_EXIT, Outcome.INVALID_EXAMPLE),
        (125, Outcome.SETUP_ERROR),
    ],
)
def test_exit_code_to_outcome(fake_docker, exit_code, outcome):
    docker = fake_docker(run_results=[exit_code])
    result = Runner(docker).run(release_target("demo", "3.12"), "assert False\n")
    assert result.outcome is outcome
    assert docker.snippets == ["assert False\n"]


def test_timeout_removes_container(fake_docker):
    docker = fake_docker(run_results=["timeout"])
    result = Runner(docker, timeout=1).run(release_target("demo", "3.12"), "while True: pass\n")
    assert result.outcome is Outcome.TIMED_OUT
    assert docker.calls[-1][:3] == ["docker", "rm", "-f"]


def test_build_failure_is_a_setup_error(fake_docker):
    docker = fake_docker(build_fails={"release"})
    result = Runner(docker).run(release_target("not-a-package", "3.12"), "x = 1\n")
    assert result.outcome is Outcome.SETUP_ERROR
    assert "could not install" in result.output
    assert not any(call[1] == "run" for call in docker.calls)


def test_main_target_builds_from_source(fake_docker, tmp_path):
    docker = fake_docker(run_results=[0])
    Runner(docker).run(main_target(tmp_path, "3.12"), "x = 1\n")
    build = docker.calls[0]
    assert build[1] == "build"
    assert build[-1] == str(tmp_path)
