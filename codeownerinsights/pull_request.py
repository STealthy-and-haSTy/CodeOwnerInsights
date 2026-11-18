from pathlib import Path
from typing import List, Optional

from .codeowners import CODEOWNERS_LOCATIONS, CodeOwnerSpecification, parse_code_owners
from .git import (
    DEFAULT_GIT,
    get_git_changed_files_compared_to_branch,
    get_git_untracked_files,
    read_file_at_ref,
)

PULL_REQUEST_DIFF_FILTER = 'ACMRD'


def get_pull_request_changed_files(
    repo_root: Path, base: str, git: str = DEFAULT_GIT, with_uncommitted: bool = False
) -> List[Path]:
    """Committed changes only, deletions included. ``with_uncommitted`` adds the working tree and untracked files."""
    changed = list(
        get_git_changed_files_compared_to_branch(
            repo_root,
            base,
            git=git,
            diff_filter=PULL_REQUEST_DIFF_FILTER,
            head=None if with_uncommitted else 'HEAD',
        )
    )
    if not with_uncommitted:
        return changed
    return sorted(set(changed + get_git_untracked_files(repo_root, git=git)))


def get_code_owner_specifications_at_ref(
    repo_root: Path, ref: str, git: str = DEFAULT_GIT
) -> Optional[List[CodeOwnerSpecification]]:
    for location in CODEOWNERS_LOCATIONS:
        content = read_file_at_ref(repo_root, ref, location, git=git)
        if content is not None:
            return list(parse_code_owners(repo_root / location, content))
    return None
