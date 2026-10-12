import json

import pytest

from repro_check import cli
from repro_check.github import find_previous_comment
from repro_check.report import MARKER

BODY = "### Reproduction\n\n```python\nimport demo\nassert demo.add(2, 2) == 4\n```\n"


@pytest.fixture
def project(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    return tmp_path


@pytest.fixture
def github_env(tmp_path, monkeypatch):
    for name in ("INPUT_PACKAGE", "INPUT_MAIN_PATH", "INPUT_COMMENT", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    output = tmp_path / "output"
    summary = tmp_path / "summary"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    return output, summary


def test_local_run_with_both_targets(tmp_path, project, fake_docker, github_env, capsys):
    body = tmp_path / "issue.md"
    body.write_text(BODY)
    docker = fake_docker(run_results=[1, 0])

    code = cli.main(
        ["--body-file", str(body), "--package", "demo", "--main-path", str(project)],
        executor=docker,
    )

    assert code == 0
    out = capsys.readouterr().out
    assert "Probably already fixed" in out
    assert docker.snippets == ["import demo\nassert demo.add(2, 2) == 4\n"] * 2
    output, summary = github_env
    assert output.read_text() == "verdict=fixed-on-main\n"
    assert MARKER in summary.read_text()


def test_issue_without_example_runs_nothing(tmp_path, fake_docker, github_env, capsys):
    body = tmp_path / "issue.md"
    body.write_text("It crashes.")
    docker = fake_docker()

    assert cli.main(["--body-file", str(body), "--package", "demo"], executor=docker) == 0
    assert docker.calls == []
    assert "No runnable example" in capsys.readouterr().out


def test_event_mode_posts_comment(tmp_path, fake_docker, github_env, monkeypatch):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"issue": {"number": 42, "body": BODY}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_REPOSITORY", "octo/demo")
    monkeypatch.setenv("REPRO_CHECK_TOKEN", "t0ken")
    posted = {}

    def fake_upsert(self, repo, number, body):
        posted.update(repo=repo, number=number, body=body)
        return "https://github.com/octo/demo/issues/42#issuecomment-1"

    monkeypatch.setattr(cli.GitHub, "upsert_comment", fake_upsert)

    assert cli.main(["--package", "demo"], executor=fake_docker(run_results=[1])) == 0
    assert posted["repo"] == "octo/demo"
    assert posted["number"] == 42
    assert "Reproduced" in posted["body"]


def test_pull_request_events_are_ignored(tmp_path, fake_docker, github_env, monkeypatch):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"issue": {"number": 1, "body": BODY, "pull_request": {}}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    docker = fake_docker()
    assert cli.main(["--package", "demo"], executor=docker) == 0
    assert docker.calls == []


def test_nothing_to_test_is_an_error(tmp_path, github_env, capsys):
    body = tmp_path / "issue.md"
    body.write_text(BODY)
    assert cli.main(["--body-file", str(body)]) == 2
    assert "nothing to test" in capsys.readouterr().err


def test_main_path_must_be_a_python_project(tmp_path, github_env, capsys):
    body = tmp_path / "issue.md"
    body.write_text(BODY)
    assert cli.main(["--body-file", str(body), "--main-path", str(tmp_path)]) == 2
    assert "no Python project" in capsys.readouterr().err


def test_find_previous_comment_only_trusts_bots():
    comments = [
        {"id": 1, "body": f"{MARKER} old", "user": {"type": "Bot"}},
        {"id": 2, "body": f"quoting {MARKER}", "user": {"type": "User"}},
        {"id": 3, "body": f"{MARKER} newer", "user": {"type": "Bot"}},
        {"id": 4, "body": "unrelated", "user": {"type": "Bot"}},
    ]
    assert find_previous_comment(comments)["id"] == 3
    assert find_previous_comment(comments[1:2]) is None
