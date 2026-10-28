import functools
import re
from collections import deque
from pathlib import Path, PurePath
from typing import Iterable, Optional, Pattern, Tuple
from dataclasses import dataclass
from wcmatch.glob import translate, CASE, DOTGLOB, FORCEUNIX, GLOBSTAR

# https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners

# Characters that wcmatch treats as glob syntax but GitHub's CODEOWNERS docs
# say do not work. They must be matched literally, so the pattern is escaped
# before being handed to wcmatch. ``*``, ``?`` and ``**`` are left alone --
# those are the wildcards CODEOWNERS does support.
_LITERAL_GLOB_CHARS = str.maketrans({'[': r'\[', ']': r'\]'})


@functools.lru_cache(maxsize=None)
def _compile_codeowner_glob(glob_pattern: str) -> Optional[Tuple[str, Pattern[str]]]:
    # Any path the pattern matches contains its longest wildcard-free run, so a
    # substring check rules out most paths without running the regex.
    required_literal = max(re.split(r'[*?/]', glob_pattern), key=len)
    glob_pattern = glob_pattern.translate(_LITERAL_GLOB_CHARS)
    directory_only = glob_pattern.endswith('/')
    body = glob_pattern.strip('/')
    if body == '':
        return None
    # A slash at the start or in the middle anchors the pattern to the root;
    # a trailing slash alone does not.
    anchored = glob_pattern.startswith('/') or '/' in body

    patterns_to_try = list()
    if not directory_only:
        patterns_to_try.append(body)
    # GitHub keeps `docs/*` to the files directly inside `docs`.
    if directory_only or body.split('/')[-1] != '*':
        patterns_to_try.append(body + '/**')
    if not anchored:
        patterns_to_try = ['**/' + pattern for pattern in patterns_to_try]

    # GitHub's matching does not vary by platform, while wcmatch's defaults do.
    regexes, _ = translate(
        patterns_to_try, flags=GLOBSTAR | DOTGLOB | CASE | FORCEUNIX
    )
    return required_literal, re.compile('|'.join(regexes))


def does_codeowner_glob_match(glob_pattern: str, path: PurePath) -> bool:
    compiled = _compile_codeowner_glob(glob_pattern)
    if compiled is None:
        return False
    required_literal, regex = compiled
    posix_path = path.as_posix() if isinstance(path, PurePath) else str(path)
    if required_literal not in posix_path:
        return False
    return regex.match(posix_path.lstrip('/')) is not None


@dataclass
class CodeOwnerSpecification:
    """Data class for showing the code owner specification parsed from a line in a CODEOWNERS file."""

    nearest_comment: Optional[str]
    glob_pattern: str
    owners: list  # [str]
    line_number: int
    codeowners_file_path: Path

    def does_match(self, path: Path) -> bool:
        return does_codeowner_glob_match(self.glob_pattern, path)


def parse_code_owners(
    codeowners_file_path: Path, codeowners_content: str
) -> Iterable[CodeOwnerSpecification]:
    last_comment = None
    line_number = 0
    prev_line_was_a_rule = False
    for line in codeowners_content.splitlines():
        line_number += 1
        if line.lstrip().startswith('#'):
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
        glob_pattern, *owners = line.split()

        yield CodeOwnerSpecification(
            last_comment, glob_pattern, owners, line_number, codeowners_file_path
        )


def get_matching_code_owner_specifications_for_file(
    codeowners: Iterable[CodeOwnerSpecification], path: Path
) -> Iterable[CodeOwnerSpecification]:
    for owner_specification in codeowners:
        if owner_specification.does_match(path):
            yield owner_specification


def get_resolved_code_owners_for_file(
    codeowners: Iterable[CodeOwnerSpecification], path: Path
) -> Optional[CodeOwnerSpecification]:
    # TODO: option to skip * root entry

    queue = deque(get_matching_code_owner_specifications_for_file(codeowners, path), maxlen=1)
    if queue:
        last_element = queue.pop()
        return last_element

    return None


def get_code_owners_file(repo_root: Path) -> Optional[Path]:
    try_locations = ['./.github/', './', './docs']
    # If CODEOWNERS files exist in more than one of those locations, GitHub will search for them in that order and use the first one it finds.

    for folder in try_locations:
        path = repo_root / folder / 'CODEOWNERS'
        if path.is_file():
            return path

    return None


def is_path_relative_to(path: Path, possible_ancestor_folder: Path) -> bool:
    try:
        path.relative_to(possible_ancestor_folder)
        return True
    except ValueError:
        return False
