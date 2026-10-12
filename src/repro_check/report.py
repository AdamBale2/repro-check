"""Write the comment posted on the issue."""

from __future__ import annotations

import re

from .runner import Outcome, RunResult
from .verdict import Verdict

MARKER = "<!-- repro-check -->"
SHOWN_OUTPUT_CHARS = 3_000

HEADLINES = {
    Verdict.REPRODUCED: "🔴 **Reproduced.** The example fails on every version tested.",
    Verdict.FIXED_ON_MAIN: (
        "🟢 **Probably already fixed.** The example fails on the latest release"
        " but passes on the default branch."
    ),
    Verdict.REGRESSION: (
        "🟠 **Possible regression.** The example passes on the latest release"
        " but fails on the default branch."
    ),
    Verdict.NOT_REPRODUCED: "⚪ **Not reproduced.** The example runs without error.",
    Verdict.NO_EXAMPLE: "📝 **No runnable example found** in this issue.",
    Verdict.INVALID_EXAMPLE: "📝 **The example is not valid Python**, so it could not be run.",
    Verdict.INCONCLUSIVE: (
        "⚠️ **Inconclusive.** At least one run timed out or could not be set up."
    ),
}

OUTCOME_LABELS = {
    Outcome.PASSED: "✅ passes",
    Outcome.FAILED: "❌ fails",
    Outcome.TIMED_OUT: "⏱️ timed out",
    Outcome.INVALID_EXAMPLE: "📝 invalid example",
    Outcome.SETUP_ERROR: "⚠️ setup error",
}


def how_to_write_an_example(timeout: float) -> str:
    return (
        "To get an automatic check, add a minimal, self-contained example in a"
        " ```` ```python ```` block under a `### Reproduction` heading. It should:\n\n"
        "- raise an exception or fail an `assert` while the bug is present;\n"
        f"- finish in under {timeout:g} seconds;\n"
        "- not need network access, files or credentials."
    )


def render(
    verdict: Verdict,
    results: list[RunResult],
    *,
    python_version: str,
    timeout: float,
    note: str | None = None,
) -> str:
    parts = [MARKER, HEADLINES[verdict]]

    if note:
        parts.append(note)

    if verdict in (Verdict.NO_EXAMPLE, Verdict.INVALID_EXAMPLE):
        parts.append(how_to_write_an_example(timeout))

    if results:
        rows = ["| Version | Result | Time |", "| --- | --- | --- |"]
        for r in results:
            status = OUTCOME_LABELS[r.outcome]
            if r.outcome is Outcome.FAILED:
                status += f" (exit {r.exit_code})"
            rows.append(f"| {r.target.label} | {status} | {r.duration:.1f} s |")
        parts.append("\n".join(rows))

        for r in results:
            if r.output.strip():
                parts.append(
                    f"<details><summary>Output: {r.target.label}</summary>\n\n"
                    f"{code_block(tail(r.output))}\n\n</details>"
                )

    parts.append(
        "<sub>Automatic check by repro-check: the example ran on Python"
        f" {python_version} in an isolated container with no network access."
        " A maintainer will still look at this issue.</sub>"
    )
    return "\n\n".join(parts) + "\n"


def tail(text: str, limit: int = SHOWN_OUTPUT_CHARS) -> str:
    text = text.rstrip()
    if len(text) <= limit:
        return text
    return "[…]\n" + text[-limit:]


def code_block(text: str) -> str:
    """A fenced block that the content cannot close early."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text}\n{fence}"
