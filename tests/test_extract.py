import pytest

from repro_check.extract import (
    MAX_SNIPPET_CHARS,
    SnippetTooLarge,
    find_reproduction,
    iter_code_blocks,
)

ISSUE_FORM_BODY = """\
### Description

Adding two numbers returns the wrong result.

```text
this is not code
```

### Reproduction

```python
import demo

assert demo.add(2, 2) == 4
```

### Version

1.2.3
"""


def test_issue_form_reproduction_block():
    assert find_reproduction(ISSUE_FORM_BODY) == "import demo\n\nassert demo.add(2, 2) == 4\n"


def test_prefers_block_under_reproduction_heading():
    body = """\
Some context:

```python
print("not the repro")
```

## Minimal reproducible example

```py
raise RuntimeError("the repro")
```
"""
    assert find_reproduction(body) == 'raise RuntimeError("the repro")\n'


def test_untagged_block_under_reproduction_heading():
    body = "### Steps to reproduce\n\n```\nimport demo\n```\n"
    assert find_reproduction(body) == "import demo\n"


def test_untagged_block_elsewhere_is_ignored():
    body = "### Logs\n\n```\nTraceback (most recent call last):\n```\n"
    assert find_reproduction(body) is None


def test_falls_back_to_first_python_block():
    body = "Hello\n\n```python\nx = 1\n```\n\n```python\ny = 2\n```\n"
    assert find_reproduction(body) == "x = 1\n"


def test_no_example():
    assert find_reproduction("It crashes, please fix.") is None
    assert find_reproduction("") is None
    assert find_reproduction(None) is None


def test_empty_block_is_skipped():
    body = "### Reproduction\n\n```python\n\n```\n\n```python\nx = 1\n```\n"
    assert find_reproduction(body) == "x = 1\n"


def test_windows_line_endings():
    body = "### Reproduction\r\n\r\n```python\r\nx = 1\r\n```\r\n"
    assert find_reproduction(body) == "x = 1\n"


def test_tilde_and_longer_fences():
    body = "````python\nprint('```')\n````\n\n~~~py\ny = 2\n~~~\n"
    blocks = iter_code_blocks(body)
    assert [b.code for b in blocks] == ["print('```')", "y = 2"]


def test_info_string_with_attributes():
    body = "```python title=repro.py\nx = 1\n```\n"
    assert find_reproduction(body) == "x = 1\n"


def test_pycon_session_keeps_only_inputs():
    body = """\
### Reproduction

```pycon
>>> import demo
>>> demo.add(2, 2)
5
>>> for i in range(2):
...     print(i)
...
0
1
```
"""
    assert find_reproduction(body) == (
        "import demo\ndemo.add(2, 2)\nfor i in range(2):\n    print(i)\n"
    )


def test_indented_fence():
    body = "  ```python\n  x = 1\n  ```\n"
    assert find_reproduction(body) == "x = 1\n"


def test_unclosed_fence_runs_to_end():
    body = "```python\nx = 1\n"
    assert find_reproduction(body) == "x = 1\n"


def test_too_large():
    body = "```python\n" + "x = 1\n" * (MAX_SNIPPET_CHARS // 6 + 10) + "```\n"
    with pytest.raises(SnippetTooLarge):
        find_reproduction(body)
