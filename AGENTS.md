# AGENTS.md

This repository contains a Sublime Text plugin for identifying code owners from CODEOWNERS files.

## Project Structure

- `codeowners.py` - Core parsing logic (pure Python, no Sublime dependencies)
- `git.py` - Git shell-outs (pure Python, no Sublime dependencies)
- `subl_codeowners.py` - Sublime Text plugin (the only module that imports `sublime`/`sublime_plugin`)
- `Default.sublime-commands` - Command palette entries
- `dependencies.json` - Vendored dependencies for Sublime's dependency manager
- `test/` - Test files

## Key Design Principles

- Core parsing logic in `codeowners.py` and `git.py` is framework-agnostic and independently testable
- No Sublime Text APIs outside `subl_codeowners.py` - keeps business logic pure
- All packages in the Python 3.8 plugin host share a single interpreter process, so never mutate process-global state. In particular `git.py` must not call `os.chdir()`: it would change the working directory for every other package for the rest of the session. Pass `cwd=` to `subprocess.run()` instead.
- Uses `wcmatch` for GitHub-compatible glob pattern matching

## Runtime Environment

The plugin runs inside Sublime Text's Python 3.8 plugin host, and `.python-version` pins 3.8. The development virtualenv may be a newer Python, so keep code to syntax and stdlib APIs available in 3.8.

## Development Commands

```bash
# Install dependencies (Poetry manages the virtualenv; there is no in-repo .venv)
poetry install --no-root

# Run tests - must be invoked as `python3 -m pytest`, a bare `pytest` fails
# to import the repo's modules
poetry run python3 -m pytest

# Run a single test file
poetry run python3 -m pytest test/test_git.py
```

## Formatting

There is no formatter config committed. The editor's ruff integration (0.12.x) reformats Python files on save using its defaults, so expect unrelated reformatting to show up in diffs alongside your own edits. Keep that reformatting in a separate commit so functional changes stay reviewable.

## Testing

Tests are in the `test/` directory and use pytest. Everything except `subl_codeowners.py` is covered, and nothing requires a running Sublime Text.

- `test_parsing.py`, `test_matching.py`, `test_utils.py` - `codeowners.py`
- `test_git.py` - `git.py`. Builds real temporary repositories in `tmp_path` (including a bare `origin` so `origin/HEAD` resolves) and shells out to git. No network access, and no test may mutate the process working directory
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
- `get_resolved_code_owners_for_file()` - Finds the most specific matching owner for a file path
- `is_path_relative_to()` - Guards against applying a folder's CODEOWNERS to files outside it

## git.py Notes

- `exec_command()` passes `cwd=folder_path` to `subprocess.run()`, so every command runs against the project folder regardless of the process working directory
- `git diff --name-only` prints paths relative to the folder git was run in, not to the repo root. Join them with `folder_path` before handing them to `get_code_owner()`, which makes them relative to the folder again via `os.path.relpath()`
- `get_default_branch()` returns an empty string rather than `None` when git fails, because the `| cut` pipeline makes the exit code come from `cut`. Callers test the result for truthiness
- Renamed files are reported under their new path only, and `--diff-filter=ACMR` drops deletions

## Architecture

The separation between `codeowners.py`/`git.py` and `subl_codeowners.py` allows:
- Independent testing of core logic
- Framework-agnostic code that can be reused
- Clear boundary between business logic and UI framework
