"""codeownerinsights

Framework-agnostic helpers for parsing GitHub's CODEOWNERS file and resolving
owners for a path, plus thin wrappers around git for finding changed files.

The package is intentionally free of any editor dependency so the logic can be
imported and unit tested from any Python environment.
"""

from .codeowners import (
    CodeOwnerSpecification,
    does_codeowner_glob_match,
    get_code_owners_file,
    get_matching_code_owner_specifications_for_file,
    get_resolved_code_owners_for_file,
    is_path_relative_to,
    parse_code_owners,
)
from .status_text import (
    DEFAULT_STATUS_TEMPLATE,
    get_template_replacements,
    render_status_text,
)

__all__ = [
    'CodeOwnerSpecification',
    'DEFAULT_STATUS_TEMPLATE',
    'does_codeowner_glob_match',
    'get_code_owners_file',
    'get_matching_code_owner_specifications_for_file',
    'get_resolved_code_owners_for_file',
    'get_template_replacements',
    'is_path_relative_to',
    'parse_code_owners',
    'render_status_text',
]
