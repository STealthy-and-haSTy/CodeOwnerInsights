# CodeOwnerInsights

A Sublime Text plugin to help identify the "code owner" of the current file.
Parses GitHub's `CODEOWNERS` file and resolves the owner for the focused tab
and shows it in the status bar. Includes a command palette entry to open the
`CODEOWNERS` file at the relevant line.

The parsing, matching, and git logic live in a small framework-agnostic library
published to PyPI as [`codeownerinsights`](https://pypi.org/project/codeownerinsights/).
The plugin is just a thin Sublime wrapper around it, so the core behaviour can
be imported and unit tested from any Python environment.

## Status

This project is still in it's early stages, but works well. It was written for
my personal use, but any bugs reported will be fixed. Feature requests will be
considered, bonus points if you raise a Pull Request.

Settings live in `CodeOwnerInsights.sublime-settings` and are editable from
*Preferences → Package Settings → CodeOwnerInsights → Settings*.

There is experimental support for showing all `git` changed files compared to
the default branch, grouped by code owner. You will find it in the command
palette. Currently very ugly but gets the job done.

## Library usage

```python
from pathlib import Path
from codeownerinsights.codeowners import parse_code_owners, get_resolved_code_owners_for_file

codeowners_path = Path(".github/CODEOWNERS")
codeowners = list(parse_code_owners(codeowners_path, codeowners_path.read_text(encoding="utf-8")))
owner = get_resolved_code_owners_for_file(codeowners, Path("src/main.py"))
```

## Development

To run the parser tests, in a terminal emulator:

```sh
python3.12 -m venv ./.venv
source .venv/bin/activate
pip install poetry
poetry install --no-root
deactivate # to avoid problems later
.venv/bin/poetry run python3 -- -m pytest
```

Ideally we will get these tests running in CI also.