"""Find the reproduction example in the body of an issue."""

from __future__ import annotations

import re
from dataclasses import dataclass

PYTHON_TAGS = {"python", "py", "python3", "pycon"}
MAX_SNIPPET_CHARS = 20_000

_FENCE_OPEN = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})(?P<info>[^\n`]*)$")
_HEADING = re.compile(r"^ {0,3}#{1,6}\s+(?P<title>.*?)\s*#*\s*$")
_REPRO_WORDS = re.compile(r"repro|minimal|\bmcve\b|\bmre\b", re.IGNORECASE)


@dataclass(frozen=True)
class CodeBlock:
    language: str
    code: str
    heading: str | None


class SnippetTooLarge(ValueError):
    pass


def iter_code_blocks(body: str) -> list[CodeBlock]:
    """Return the fenced code blocks of a Markdown text, with the heading above each."""
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[CodeBlock] = []
    heading: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        opening = _FENCE_OPEN.match(line)
        if opening is None:
            title = _HEADING.match(line)
            if title:
                heading = title.group("title")
            i += 1
            continue

        fence = opening.group("fence")
        indent = len(opening.group("indent"))
        language = opening.group("info").strip().split(" ")[0].lower()
        closing = re.compile(rf"^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}\s*$")
        content: list[str] = []
        i += 1
        while i < len(lines) and not closing.match(lines[i]):
            content.append(_strip_indent(lines[i], indent))
            i += 1
        i += 1  # skip the closing fence (or run past the end if unclosed)
        blocks.append(CodeBlock(language=language, code="\n".join(content), heading=heading))
    return blocks


def find_reproduction(body: str | None) -> str | None:
    """Pick the Python example to run, or None if the issue has none.

    Preference order:
    1. a Python (or untagged) block under a heading that looks like "Reproduction",
    2. the first Python block anywhere in the issue.
    """
    if not body:
        return None
    blocks = iter_code_blocks(body)

    under_repro_heading = [
        b
        for b in blocks
        if b.heading
        and _REPRO_WORDS.search(b.heading)
        and (b.language in PYTHON_TAGS or b.language == "")
    ]
    python_blocks = [b for b in blocks if b.language in PYTHON_TAGS]
    candidates = under_repro_heading or python_blocks

    for block in candidates:
        code = _from_pycon(block.code) if block.language == "pycon" else block.code
        if code.strip():
            if len(code) > MAX_SNIPPET_CHARS:
                raise SnippetTooLarge(
                    f"the example is {len(code)} characters long (limit: {MAX_SNIPPET_CHARS})"
                )
            return code.strip("\n") + "\n"
    return None


def _strip_indent(line: str, indent: int) -> str:
    removable = len(line) - len(line.lstrip(" "))
    return line[min(indent, removable) :]


def _from_pycon(code: str) -> str:
    """Keep only the input lines of an interactive session (>>> and ...)."""
    kept = []
    for line in code.split("\n"):
        if line.startswith(">>> ") or line == ">>>" or line.startswith("... ") or line == "...":
            kept.append(line[4:])
    return "\n".join(kept)
