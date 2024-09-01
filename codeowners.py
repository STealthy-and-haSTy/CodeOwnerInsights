from collections import deque
from pathlib import Path
from typing import Iterable, Optional, Union
from dataclasses import dataclass


# https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners

@dataclass
class CodeOwnerSpecification:
    """Data class for showing the code owner specification parsed from a line in a CODEOWNERS file."""
    nearest_comment: Optional[str]
    glob_pattern: str
    owners: list #[str]
    line_number: int

    def does_match(self, path: Path) -> bool:
        patterns_to_try = list()
        if self.glob_pattern.endswith('/'):
            patterns_to_try.append(self.glob_pattern + '**')
        else:
            patterns_to_try.append(self.glob_pattern)
            patterns_to_try.append(self.glob_pattern + '.*') # extension if unspecified is irrelevant, base name is matched

        return any((path.match(pattern) for pattern in patterns_to_try))


def parse_code_owners(codeowners_content: str) -> Iterable[CodeOwnerSpecification]:
    last_comment = None
    line_number = 0
    for line in codeowners_content.splitlines():
        line_number += 1
        if line.startswith('#'):
            last_comment = line
            continue

        if line.strip() == '':
            last_comment = None
            continue
        
        # assume no spaces in file path glob for now
        glob_pattern, owners = line.split(' ', maxsplit=1)
        yield CodeOwnerSpecification(last_comment, glob_pattern, owners.split(), line_number)


def get_matching_code_owner_specifications_for_file(codeowners: Iterable[CodeOwnerSpecification], path: Path) -> Iterable[CodeOwnerSpecification]:
    for owner_specification in codeowners:
        if owner_specification.does_match(path):
            yield owner_specification


def get_resolved_code_owners_for_file(codeowners: Iterable[CodeOwnerSpecification], path: Path) -> Optional[CodeOwnerSpecification]:
    # TODO: option to skip * root entry
    
    queue = deque(get_matching_code_owner_specifications_for_file(codeowners, path), maxlen=1)
    if queue:
        last_element = queue.pop()
        return last_element

    return None


def get_code_owners_file(repo_root: Path) -> Optional[Path]:
    try_locations = [ './.github/', './', './docs']
    # If CODEOWNERS files exist in more than one of those locations, GitHub will search for them in that order and use the first one it finds.
    
    for folder in try_locations:
        path = repo_root / folder / 'CODEOWNERS'
        if path.is_file():
            return path

    return None


def test_parsing() -> bool:
    from textwrap import dedent

    codeowners_content = dedent("""\
        # Code
        * @org/some-team

        # tracking database migrations
        source/migrations/ @org/db-admins

        # infrastructure related
        terraform/ @org/infra
        **/Dockerfile @org/infra
    """)
    codeowners = list(parse_code_owners(codeowners_content))

    owner = get_resolved_code_owners_for_file(codeowners, Path('source/migrations/20240831-223245-some_file.sql'))
    print(owner)
    expected_owner = CodeOwnerSpecification(
        '# tracking database migrations',
        'source/migrations/',
        ['@org/db-admins'],
        5
    )

    test_succeeds = owner == expected_owner
    print(test_succeeds)
    assert test_succeeds # assertions are ignored in ST unfortunately
    return test_succeeds
