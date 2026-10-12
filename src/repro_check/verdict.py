"""Turn per-target results into a single verdict."""

from __future__ import annotations

from enum import Enum

from .runner import Outcome, RunResult


class Verdict(str, Enum):
    REPRODUCED = "reproduced"
    FIXED_ON_MAIN = "fixed-on-main"
    REGRESSION = "regression"
    NOT_REPRODUCED = "not-reproduced"
    NO_EXAMPLE = "no-example"
    INVALID_EXAMPLE = "invalid-example"
    INCONCLUSIVE = "inconclusive"


def decide(results: list[RunResult]) -> Verdict:
    """An example "fails" when it raises or fails an assert: that means the bug is present."""
    if not results:
        return Verdict.NO_EXAMPLE
    if any(r.outcome is Outcome.INVALID_EXAMPLE for r in results):
        return Verdict.INVALID_EXAMPLE
    if not all(r.outcome.conclusive for r in results):
        return Verdict.INCONCLUSIVE

    failed = {r.target.key: r.outcome is Outcome.FAILED for r in results}
    if "release" in failed and "main" in failed:
        if failed["release"] and failed["main"]:
            return Verdict.REPRODUCED
        if failed["release"]:
            return Verdict.FIXED_ON_MAIN
        if failed["main"]:
            return Verdict.REGRESSION
        return Verdict.NOT_REPRODUCED
    return Verdict.REPRODUCED if any(failed.values()) else Verdict.NOT_REPRODUCED
