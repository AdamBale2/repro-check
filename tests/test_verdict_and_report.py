import pytest

from repro_check.report import MARKER, code_block, render
from repro_check.runner import Outcome, RunResult, Target
from repro_check.verdict import Verdict, decide

RELEASE = Target("release", "Latest release (`demo`)", "", None)
MAIN = Target("main", "Default branch", "", None)


def result(target, outcome, output="", exit_code=None):
    if exit_code is None:
        exit_code = {Outcome.PASSED: 0, Outcome.FAILED: 1}.get(outcome)
    return RunResult(target, outcome, exit_code, 1.234, output)


P, F = Outcome.PASSED, Outcome.FAILED


@pytest.mark.parametrize(
    ("release", "main", "verdict"),
    [
        (F, F, Verdict.REPRODUCED),
        (F, P, Verdict.FIXED_ON_MAIN),
        (P, F, Verdict.REGRESSION),
        (P, P, Verdict.NOT_REPRODUCED),
        (F, Outcome.TIMED_OUT, Verdict.INCONCLUSIVE),
        (Outcome.SETUP_ERROR, P, Verdict.INCONCLUSIVE),
        (Outcome.INVALID_EXAMPLE, Outcome.INVALID_EXAMPLE, Verdict.INVALID_EXAMPLE),
    ],
)
def test_two_targets(release, main, verdict):
    assert decide([result(RELEASE, release), result(MAIN, main)]) is verdict


@pytest.mark.parametrize(
    ("outcome", "verdict"), [(F, Verdict.REPRODUCED), (P, Verdict.NOT_REPRODUCED)]
)
@pytest.mark.parametrize("target", [RELEASE, MAIN])
def test_single_target(target, outcome, verdict):
    assert decide([result(target, outcome)]) is verdict


def test_no_results():
    assert decide([]) is Verdict.NO_EXAMPLE


def test_report_contents():
    results = [
        result(RELEASE, F, "Traceback (most recent call last):\nAssertionError"),
        result(MAIN, P),
    ]
    text = render(Verdict.FIXED_ON_MAIN, results, python_version="3.12", timeout=60)
    assert text.startswith(MARKER)
    assert "Probably already fixed" in text
    assert "| Latest release (`demo`) | ❌ fails (exit 1) | 1.2 s |" in text
    assert "| Default branch | ✅ passes | 1.2 s |" in text
    assert "AssertionError" in text
    assert "Python 3.12" in text


def test_report_explains_how_to_write_an_example():
    text = render(Verdict.NO_EXAMPLE, [], python_version="3.12", timeout=30)
    assert "### Reproduction" in text
    assert "under 30 seconds" in text


def test_output_cannot_escape_its_code_block():
    hostile = "```\n</details>\n@everyone **bold** ````"
    block = code_block(hostile)
    fence = block.split("text\n", 1)[0]
    assert len(fence) == 5  # longer than the longest backtick run in the output
    assert block.endswith("\n" + fence)


def test_long_output_is_truncated():
    results = [result(RELEASE, F, "x" * 10_000 + "END")]
    text = render(Verdict.REPRODUCED, results, python_version="3.12", timeout=60)
    assert "END" in text
    assert len(text) < 5_000
