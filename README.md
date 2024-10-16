# CodeOwnerInsights
Sublime Text plugin to help identify the "code owner" of the current file.
Parses GitHub's `CODEOWNERS` file and resolves the owner for the focused tab and shows it in the status bar.
Includes a command pallete entry to open the `CODEOWNERS` file at the relevant line.

## Status
This project is still in it's early stages, but works well. It was written for my personal use, but any bugs reported will be fixed. Feature requests will be considered, bonus points if you raise a Pull Request.
There is currently no support for configuration, but it is planned to allow to customize what gets shown in the status bar.

There is experimental support for showing all `git` changed files compared to the default branch, grouped by code owner. You will find it in the command palette. Currently very ugly but gets the job done 

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
