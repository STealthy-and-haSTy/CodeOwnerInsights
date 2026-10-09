# AGENTS.md

This repository contains a Sublime Text plugin for identifying code owners from CODEOWNERS files.

## Project Structure

- `codeownerinsights/` - The publishable library (pure Python, no Sublime dependencies)
  - `codeowners.py` - Core parsing logic
  - `git.py` - Git shell-outs
  - `coercion.py` - Value-narrowing helpers for settings and command arguments
  - `status_text.py` - Status bar template substitution
  - `__init__.py` - Re-exports the public API
- `subl_codeowners.py` - Sublime Text plugin (the only module that imports `sublime`/`sublime_plugin`)
- `Default.sublime-commands` - Command palette entries
- `dependencies.json` - Vendored dependencies for Sublime's dependency manager
- `test/` - Test files

## Key Design Principles

- Core parsing logic in `codeownerinsights/codeowners.py` and `codeownerinsights/git.py` is framework-agnostic and independently testable
- No Sublime Text APIs outside `subl_codeowners.py` - keeps business logic pure
- Keep any logic worth asserting on out of `subl_codeowners.py` and in a pure module, so it can be unit tested. `coercion.py` exists because `subl_codeowners.py` cannot be imported outside the editor
- All packages in the Python 3.8 plugin host share a single interpreter process, so never mutate process-global state. In particular `git.py` must not call `os.chdir()`: it would change the working directory for every other package for the rest of the session. Pass `cwd=` to `subprocess.run()` instead.
- Uses `wcmatch` for GitHub-compatible glob pattern matching
- The library is published to PyPI as `codeownerinsights`, so the package directory is the source of truth. The plugin imports from it via relative imports (`from .codeownerinsights.codeowners import ...`).

## Runtime Environment

The plugin runs inside Sublime Text's Python 3.8 plugin host, and `.python-version` pins 3.8. The development virtualenv may be a newer Python, so keep code to syntax and stdlib APIs available in 3.8.

## Development Commands

```bash
# Install dependencies (Poetry manages the virtualenv; there is no in-repo .venv)
poetry install --no-root

# Run tests
poetry run pytest

# Run a single test file
poetry run pytest test/test_git.py
```

## Formatting

There is no formatter config committed. The editor's ruff integration (0.12.x) reformats Python files on save using its defaults, so expect unrelated reformatting to show up in diffs alongside your own edits. Keep that reformatting in a separate commit so functional changes stay reviewable.

## Testing

Tests are in the `test/` directory and use pytest. Everything except `subl_codeowners.py` is covered, and nothing requires a running Sublime Text. `[tool.pytest.ini_options]` in `pyproject.toml` puts the repo root on `sys.path` and defaults `testpaths` to `test/`, since the modules under test are not installed as a package.

- `test_parsing.py`, `test_matching.py`, `test_utils.py` - `codeownerinsights/codeowners.py`
- `test_git.py` - `codeownerinsights/git.py`. Builds real temporary repositories in `tmp_path` (including a bare `origin` so `origin/HEAD` resolves) and shells out to git. No network access, and no test may mutate the process working directory
- `test_coercion.py` - `codeownerinsights/coercion.py`. Covers the spellings a user can write in a settings file or keybinding, including the malformed ones that must fall back to the default rather than flip the setting
- `test_status_text.py` - `codeownerinsights/status_text.py`. `test_default_template_renders_as_before` pins the default template to the hardcoded string the plugin used before the status bar became configurable; change it only when that visible output is meant to change
- `subl_codeowners.py` is untested, as importing it requires the `sublime` module

## Dependencies

- `wcmatch` - For GitHub-compatible glob pattern matching
- `pytest` - For testing

## File Location Logic

The plugin searches for CODEOWNERS files in this order:
1. `./.github/CODEOWNERS`
2. `./CODEOWNERS`
3. `./docs/CODEOWNERS`

## Core Concepts

- `CodeOwnerSpecification` - Data class representing a parsed CODEOWNERS line
- `parse_code_owners()` - Parses CODEOWNERS content into specifications
- `get_matching_code_owner_specifications_for_file()` - Finds every CODEOWNERS rule that matches a file path
- `get_resolved_code_owners_for_file()` - Finds the most specific matching owner for a file path
- `is_path_relative_to()` - Guards against applying a folder's CODEOWNERS to files outside it

## Pattern matching (`does_codeowner_glob_match`)

Paths are matched relative to the repository root and carry no leading slash, so
a leading `/` on a pattern is stripped before matching as well as kept — the
slashed form anchors to the root, the unslashed form is what actually matches
relative paths. A trailing `/` matches the directory and its contents.

Two rules that follow GitHub's semantics rather than `git check-ignore`:

- An unslashed directory pattern matches the directory wherever it sits in the
  tree, not only at the root. `apps/` matches `apps/foo.js` *and*
  `src/apps/foo.js`. A leading `/` anchors to the root, so `/apps/` matches
  `apps/foo.js` but not `src/apps/foo.js`.
- `docs/*` matches one level only; `docs/` matches the directory and its
  subdirectories.

These agree with `git check-ignore`, which is the part `test/test_matching.py`
pins against hardcoded cases (the harness is pure pytest, it never shells out
to git). The two diverge elsewhere: `git check-ignore` additionally supports
`!` to negate a pattern, `\` to escape a leading `#`, and `[ ]` character
classes, all of which GitHub's `CODEOWNERS` docs list as unsupported. Brackets
are therefore escaped before matching so they're treated literally -- the
harness does exercise that case.

## git.py Notes

- `exec_command()` passes `cwd=folder_path` to `subprocess.run()`, so every command runs against the project folder regardless of the process working directory
- `git diff --name-only` prints paths relative to the folder git was run in, not to the repo root. Join them with `folder_path` before handing them to `get_code_owner()`, which makes them relative to the folder again via `os.path.relpath()`
- `get_default_branch()` returns an empty string rather than `None` when git fails, because the `| cut` pipeline makes the exit code come from `cut`. Callers test the result for truthiness
- Renamed files are reported under their new path only, and `--diff-filter=ACMR` drops deletions
- All git helpers accept an optional `git` parameter (default `"git"`) so a git wrapper can be substituted by replacing the leading command token

## Architecture

The separation between `codeownerinsights/` and `subl_codeowners.py` allows:
- Independent testing of core logic
- Framework-agnostic code that can be reused
- Clear boundary between business logic and UI framework
- The library is published to PyPI as `codeownerinsights` for reuse outside the editor