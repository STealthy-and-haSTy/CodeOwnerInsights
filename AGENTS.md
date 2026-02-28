# AGENTS.md

This repository contains a Sublime Text plugin for identifying code owners from CODEOWNERS files.

## Project Structure

- `codeowners.py` - Core parsing logic (pure Python, no Sublime dependencies)
- `subl_codeowners.py` - Sublime Text plugin (depends on Sublime API)
- `test/` - Test files

## Key Design Principles

- Core parsing logic in `codeowners.py` is framework-agnostic and independently testable
- No Sublime Text APIs in core files - keeps business logic pure
- Uses `wcmatch` for GitHub-compatible glob pattern matching

## Development Commands

```bash
# Install dependencies
poetry install --no-root

# Run tests
.venv/bin/poetry run python3 -m pytest
```

## Testing

Tests are in the `test/` directory and use pytest. The core parsing logic is thoroughly tested without requiring Sublime Text.

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

## Architecture

The separation between `codeowners.py` and `subl_codeowners.py` allows:
- Independent testing of core logic
- Framework-agnostic code that can be reused
- Clear boundary between business logic and UI framework
