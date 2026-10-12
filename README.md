# repro-check

**Does this bug report actually reproduce?** repro-check answers that for you.

repro-check is a GitHub Action for maintainers of Python projects. When a bug report
contains a reproduction example, it runs the example in an isolated container, on the
latest release **and** on your default branch, then comments the result on the issue:

> 🟢 **Probably already fixed.** The example fails on the latest release but passes on the default branch.
>
> | Version | Result | Time |
> | --- | --- | --- |
> | Latest release (`yourpackage`) | ❌ fails (exit 1) | 2.1 s |
> | Default branch | ✅ passes | 1.9 s |

Trying to reproduce bug reports by hand is one of the most time-consuming parts of
maintaining a project, and the number of low-effort reports keeps growing. repro-check
does the first pass, so you can spend your time on the issues that need you.

> **Status: early prototype (v0.1).** Python only for now. Feedback from maintainers
> is very welcome: open an issue and tell us what would make this useful for you.

## What you get

| Verdict | Meaning |
| --- | --- |
| 🔴 `reproduced` | The example fails on every version tested. |
| 🟢 `fixed-on-main` | Fails on the latest release, passes on the default branch. |
| 🟠 `regression` | Passes on the latest release, fails on the default branch. |
| ⚪ `not-reproduced` | The example runs without error. |
| 📝 `no-example` / `invalid-example` | No runnable example; the comment explains how to write one. |
| ⚠️ `inconclusive` | A run timed out or could not be set up. |

An example **fails** when it raises an exception or fails an `assert`. That is the one
convention reporters need to follow, and the comment explains it when it is missing.

The verdict is also an output of the action, so you can add labels, close stale
reports or ping someone in later steps.

## Quick start

1. Copy [`examples/workflow.yml`](examples/workflow.yml) to `.github/workflows/repro-check.yml`
   and set `package:` to your package name on PyPI.
2. Optionally copy [`examples/bug_report.yml`](examples/bug_report.yml) to
   `.github/ISSUE_TEMPLATE/` so reporters get a "Reproduction" field.
3. Add the `needs-repro` label to a bug report. repro-check comments within a minute or two.

```yaml
on:
  issues:
    types: [labeled]

permissions:
  contents: read
  issues: write

jobs:
  repro:
    if: github.event.label.name == 'needs-repro'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: AdamBale2/repro-check@v0.1.0
        with:
          package: yourpackage
```

### Inputs

| Input | Default | Description |
| --- | --- | --- |
| `package` | `""` | pip requirement for the latest release. Empty: test only the default branch. |
| `main-path` | `.` | Source tree to test as the default branch. Empty: test only the release. |
| `python-version` | `3.12` | Python version used to run the example. |
| `timeout` | `60` | Seconds allowed for the example on each version. |
| `comment` | `true` | Post the result on the issue. |
| `github-token` | `github.token` | Token used to comment. Needs `issues: write`. |

## How it finds the example

repro-check takes the first Python code block under a heading that contains
"Reproduction" (or "minimal", "MRE", "MCVE"), which is what the issue template produces.
Otherwise it takes the first block tagged `python`. Interactive sessions in `pycon`
blocks work too: only the `>>>` lines are run.

## Security

repro-check runs code written by strangers, so isolation is the core of the design:

- the example runs in a container with **no network**, a **read-only** filesystem
  (except a small `/tmp`), no Linux capabilities, an unprivileged user, and limits on
  memory, CPU, processes and time;
- **no secrets** reach the container: no environment variables from the runner, and the
  default branch is installed from a wheel built in a separate stage, so the final image
  contains neither your repository nor its `.git` directory;
- issue content is never interpolated into a shell command;
- by default the check only runs when a maintainer adds a label, so nobody can spend
  your Actions minutes by opening issues.

Found a way around this? Please read [SECURITY.md](SECURITY.md) and report it privately.

## Running it locally

```bash
pip install -e .
repro-check --body-file issue.md --package yourpackage --main-path . --no-comment
```

You need Docker. The report is printed to the terminal.

## Roadmap

- [ ] Trigger from a `/repro` comment by a maintainer
- [ ] Show the installed version of each target in the report
- [ ] Dependencies declared in the issue (`# requires: numpy`)
- [ ] JavaScript (npm), then Rust (cargo)
- [ ] Test across several Python versions in one run

## Contributing

Contributions are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md). Good first steps:
try repro-check on your own project and tell us where it got the verdict wrong.

## License

[MIT](LICENSE)
