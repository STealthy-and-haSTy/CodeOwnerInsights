from collections import deque
from pathlib import Path
from typing import Iterable, Optional, Union
from dataclasses import dataclass
from wcmatch.glob import globmatch, GLOBSTAR

# https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners

def does_codeowner_glob_match(glob_pattern: str, path: Path) -> bool:
    patterns_to_try = list()
    if glob_pattern.endswith('/'):
        patterns_to_try.append(glob_pattern + '**')
    elif glob_pattern == '*':
        return True
    elif glob_pattern.startswith('*.') and '/' not in glob_pattern:
        patterns_to_try.append('**/' + glob_pattern)
    else:
        patterns_to_try.append(glob_pattern)
        if not glob_pattern.endswith('/*'):
            if '/' in glob_pattern:
                patterns_to_try.append(glob_pattern + '/*')
            else:
                patterns_to_try.append(glob_pattern + '/**')
        if not glob_pattern.startswith('/'):
            for pattern in list(patterns_to_try):
                patterns_to_try.append('**/' + pattern)
                

    return globmatch(filename=str(path), patterns=patterns_to_try, flags=GLOBSTAR)

@dataclass
class CodeOwnerSpecification:
    """Data class for showing the code owner specification parsed from a line in a CODEOWNERS file."""
    nearest_comment: Optional[str]
    glob_pattern: str
    owners: list #[str]
    line_number: int
    codeowners_file_path: Path

    def does_match(self, path: Path) -> bool:
        return does_codeowner_glob_match(self.glob_pattern, path)


def parse_code_owners(codeowners_file_path: Path, codeowners_content: str) -> Iterable[CodeOwnerSpecification]:
    last_comment = None
    line_number = 0
    prev_line_was_a_rule = False
    for line in codeowners_content.splitlines():
        line_number += 1
        if line.startswith('#'):
            if last_comment is None or prev_line_was_a_rule:
                last_comment = line
            else:
                last_comment += '\n' + line
            prev_line_was_a_rule = False
            continue

        if line.strip() == '':
            last_comment = None
            prev_line_was_a_rule = False
            continue
        
        prev_line_was_a_rule = True
        inline_comment_pos = line.find('#')
        if inline_comment_pos > -1:
            line = line[0:inline_comment_pos]
        # assume no spaces in file path glob for now
        space_pos = line.find(' ')
        if space_pos == -1:
            glob_pattern = line
            owners = []
        else:
            glob_pattern = line[0:space_pos]
            owners = line[space_pos:].lstrip().split()
        
        yield CodeOwnerSpecification(last_comment, glob_pattern, owners, line_number, codeowners_file_path)


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
