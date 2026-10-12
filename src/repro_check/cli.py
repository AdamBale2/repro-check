"""Command-line entry point, used both locally and by the GitHub Action."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .extract import SnippetTooLarge, find_reproduction
from .github import GitHub
from .report import render
from .runner import (
    Executor,
    Runner,
    Target,
    check_python_version,
    main_target,
    release_target,
    run_command,
)
from .verdict import Verdict, decide


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repro-check",
        description=(
            "Run the reproduction example from a bug report in an isolated container,"
            " on the latest release and on the default branch, and report the result."
        ),
    )
    parser.add_argument(
        "--body-file",
        type=Path,
        help="Markdown file holding the issue body (local mode)."
        " Without it, the issue is read from the GitHub event (GITHUB_EVENT_PATH).",
    )
    parser.add_argument(
        "--package",
        default=_env("INPUT_PACKAGE", ""),
        help='pip requirement for the latest release, e.g. "requests". Empty: skip.',
    )
    parser.add_argument(
        "--main-path",
        default=_env("INPUT_MAIN_PATH", ""),
        help="Path to the source tree to test as the default branch. Empty: skip.",
    )
    parser.add_argument("--python-version", default=_env("INPUT_PYTHON_VERSION", "3.12"))
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(_env("INPUT_TIMEOUT", "60")),
        help="Seconds allowed for the example on each version (default: 60).",
    )
    parser.add_argument(
        "--no-comment",
        action="store_true",
        default=_env("INPUT_COMMENT", "true").lower() == "false",
        help="Print the report without posting it on the issue.",
    )
    parser.add_argument("--version", action="version", version=f"repro-check {__version__}")
    return parser


def main(argv: list[str] | None = None, executor: Executor = run_command) -> int:
    args = build_parser().parse_args(argv)

    try:
        check_python_version(args.python_version)
        targets = _targets(args)
        body, issue = _load_issue(args.body_file)
    except (ValueError, OSError) as exc:
        print(f"repro-check: error: {exc}", file=sys.stderr)
        return 2

    if issue is not None and issue.get("pull_request") is not None:
        print("repro-check: this is a pull request, not an issue; nothing to do.")
        return 0

    note = None
    try:
        snippet = find_reproduction(body)
    except SnippetTooLarge as exc:
        snippet, note = None, f"The example was skipped because {exc}."

    runner = Runner(executor=executor, timeout=args.timeout)
    results = [runner.run(target, snippet) for target in targets] if snippet else []
    verdict = decide(results) if snippet else Verdict.NO_EXAMPLE

    report = render(
        verdict, results, python_version=args.python_version, timeout=args.timeout, note=note
    )
    print(report)
    _write_github_files(verdict, report)

    if issue is not None and not args.no_comment:
        token = os.environ.get("REPRO_CHECK_TOKEN") or os.environ.get("GITHUB_TOKEN")
        repo = os.environ.get("GITHUB_REPOSITORY")
        if not token or not repo:
            print(
                "repro-check: no token or repository; the comment was not posted.", file=sys.stderr
            )
            return 1
        url = GitHub(token).upsert_comment(repo, int(issue["number"]), report)
        print(f"repro-check: comment posted: {url}")
    return 0


def _targets(args: argparse.Namespace) -> list[Target]:
    targets = []
    if args.package.strip():
        targets.append(release_target(args.package, args.python_version))
    if args.main_path.strip():
        source = Path(args.main_path).resolve()
        if not any((source / f).is_file() for f in ("pyproject.toml", "setup.py", "setup.cfg")):
            raise ValueError(f"no Python project (pyproject.toml or setup.py) found in {source}")
        targets.append(main_target(source, args.python_version))
    if not targets:
        raise ValueError("nothing to test: set --package, --main-path, or both")
    return targets


def _load_issue(body_file: Path | None) -> tuple[str, dict | None]:
    if body_file is not None:
        return body_file.read_text(encoding="utf-8"), None
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        raise ValueError("give --body-file, or run inside GitHub Actions on an issue event")
    with open(event_path, encoding="utf-8") as f:
        event = json.load(f)
    issue = event.get("issue")
    if not issue:
        raise ValueError("this workflow event has no issue (use `issues` or `issue_comment`)")
    return issue.get("body") or "", issue


def _write_github_files(verdict: Verdict, report: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as f:
            f.write(f"verdict={verdict.value}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(report)
