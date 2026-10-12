# Contributing to repro-check

Thanks for your interest! The project is young, so feedback counts as much as code.

## Feedback

The most useful thing right now: try repro-check on a real project and open an issue
when the verdict is wrong, the comment is confusing, or setup is harder than it should be.

## Development

```bash
git clone https://github.com/AdamBale2/repro-check
cd repro-check
pip install -e ".[dev]"
pytest          # the Docker tests are skipped if Docker is not running
ruff check .
```

The code is small and has no runtime dependencies:

| File | Role |
| --- | --- |
| `src/repro_check/extract.py` | finds the example in the issue body |
| `src/repro_check/runner.py` | builds the images and runs the example in isolation |
| `src/repro_check/verdict.py` | combines the results into a verdict |
| `src/repro_check/report.py` | writes the comment |
| `src/repro_check/github.py` | posts or updates the comment |
| `src/repro_check/cli.py` | command line, used by `action.yml` |

## Pull requests

- Keep them focused; one change per pull request.
- Add a test for any behavior change.
- Anything touching isolation (`docker_run_args`, the Dockerfiles, how issue content is
  handled) gets an extra careful review, so please explain your reasoning in the description.
