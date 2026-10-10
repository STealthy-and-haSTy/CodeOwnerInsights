# CodeOwnerInsights

A Sublime Text plugin to help identify the "code owner" of the current file.
Parses GitHub's `CODEOWNERS` file and resolves the owner for the focused tab
and shows it in the status bar. Includes command palette entries to open the
`CODEOWNERS` file at the relevant line and to list every rule that matches.

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

| Setting | Description |
| --- | --- |
| `status_bar_template` | Text shown in the status bar for the current file's code owner. See below. |
| `fetch_remote_default_branch` | Whether the diff command refreshes `origin/<default>` first, at the cost of a network round trip. |

The status bar text is a template. Wrap any of these keys in braces and they are
replaced with values from the rule that resolved for the current file:

| Key | Replaced with |
| --- | --- |
| `{owners}` | Every owner on the rule, comma separated. |
| `{owner}` | Just the first owner. |
| `{comment}` | The comment above the rule, flattened onto one line. |
| `{pattern}` | The glob pattern that matched. |
| `{line_number}` | The line the rule is on in its `CODEOWNERS` file. |
| `{codeowners_file}` | Path to the `CODEOWNERS` file the rule came from. |

The default is `"Code Owner: {comment} - {owners}"`. A key with nothing to say —
`{comment}` on a rule with no comment above it, say — renders as nothing and the
whitespace around it is collapsed, so a single template works for every rule
rather than needing a special case per rule. A misspelled key is left in place
rather than silently blanked, so it is obvious what went wrong. Setting the
template to `""` hides the status bar entirely.

There is experimental support for showing all `git` changed files compared to
the default branch, grouped by code owner. You will find it in the command
palette. Currently very ugly but gets the job done.

## Commands

| Command | Description |
| --- | --- |
| **CodeOwnerInsights: Reveal Owner** | Open the `CODEOWNERS` file on the line whose rule resolves to the current file. |
| **CodeOwnerInsights: Show All Matching Code Owner Rules** | Quick panel listing every `CODEOWNERS` rule that matches the current file, with the nearest comment shown under each pattern. The resolved owner (the last matching rule) is pre-selected. Preview opens the matching line; confirming a selection leaves the editor on that line; Esc cancels any preview navigation. |
| **CodeOwnerInsights: Show Code Owners for git changes compared to default branch** | Group all files changed relative to the default branch by their code owner. |

The "Show All Matching Code Owner Rules" command is bound to `Ctrl+Shift+O`.

## What sets this apart

Most CODEOWNERS parsers stop at the *resolved* owner — the last matching rule.
This project keeps the full match list, which is the whole point of the "Show All
Matching Code Owner Rules" command: it lets you confirm an intended rule matches
and see exactly which later line overrides it.

- **All matching rules, not just the winner.** `get_matching_code_owner_specifications_for_file`
  yields every rule that hits a path, in file order; `get_resolved_code_owners_for_file`
  returns only the last one.
- **Nearest comment carried with each rule.** Each parsed `CodeOwnerSpecification`
  remembers the comment block immediately above it, so a rule can be shown with
  its documentation rather than as a bare pattern.
- **Git-aware.** The library wraps git to enumerate changed files relative to the
  remote default branch (`origin/<default>`), refreshing the tracking ref first so
  a stale local baseline doesn't drag unrelated commits into the diff. The git
  helpers accept an optional `git=` parameter so a git wrapper can be substituted
  by replacing the leading command token.
- **GitHub's documented semantics, not git's.** Patterns follow GitHub's
  `CODEOWNERS` rules literally — a leading `/` anchors to the repo root and a
  trailing `/` matches the directory and its contents. This is deliberately not
  the `git check-ignore` convention where a leading slash means "don't match".
  Where the two diverge, we follow GitHub: `git check-ignore` additionally
  supports `!` to negate a pattern, `\` to escape a leading `#`, and `[ ]`
  character classes, all of which GitHub's `CODEOWNERS` docs list as
  unsupported. They do agree on directory and anchoring rules.

## Library usage

```python
from pathlib import Path
from codeownerinsights.codeowners import (
    parse_code_owners,
    get_matching_code_owner_specifications_for_file,
    get_resolved_code_owners_for_file,
)

codeowners_path = Path('.github/CODEOWNERS')
codeowners = list(parse_code_owners(codeowners_path, codeowners_path.read_text(encoding='utf-8')))

# every rule that matches, in file order
for spec in get_matching_code_owner_specifications_for_file(codeowners, Path('src/main.py')):
    print(spec.glob_pattern, '->', spec.owners)

# the resolved owner (last match wins)
owner = get_resolved_code_owners_for_file(codeowners, Path('src/main.py'))
```

## Development

To run the parser tests, in a terminal emulator:

```sh
python3 -m venv ./.venv
source .venv/bin/activate
pip install poetry
poetry install --no-root
deactivate # to avoid problems later
.venv/bin/poetry run pytest
```

The tests also run in CI on every push and pull request, in
[`.github/workflows/test.yml`](.github/workflows/test.yml).
