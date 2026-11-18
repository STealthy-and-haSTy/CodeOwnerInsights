import subprocess
import sys
from pathlib import Path

import pytest

from codeownerinsights.pull_request import (
    get_code_owner_specifications_at_ref,
    get_pull_request_changed_files,
)

pytestmark = pytest.mark.skipif(sys.platform == 'win32', reason='the git helpers shell out to bash')


def git(cwd: Path, *args: str) -> None:
    subprocess.run(['git', *args], cwd=str(cwd), check=True, capture_output=True)


def write_file(folder: Path, relative_path: str, content: str) -> None:
    path = folder / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def commit_all(folder: Path, message: str) -> None:
    git(folder, 'add', '-A')
    git(folder, 'commit', '-q', '-m', message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, 'init', '-q', '--initial-branch=main', 'repo')
    folder = tmp_path / 'repo'
    git(folder, 'config', 'user.name', 'CodeOwnerInsights')
    git(folder, 'config', 'user.email', 'test@example.com')
    git(folder, 'config', 'commit.gpgsign', 'false')
    write_file(folder, '.github/CODEOWNERS', '* @org/base\n')
    write_file(folder, 'kept.txt', 'kept\n')
    write_file(folder, 'removed.txt', 'removed\n')
    commit_all(folder, 'initial commit')

    git(folder, 'checkout', '-q', '-b', 'feature')
    write_file(folder, 'added.txt', 'added\n')
    (folder / 'removed.txt').unlink()
    write_file(folder, '.github/CODEOWNERS', '* @org/branch\n')
    commit_all(folder, 'feature changes')

    write_file(folder, 'kept.txt', 'edited, not committed\n')
    write_file(folder, 'untracked.txt', 'untracked\n')
    return folder


def test_changed_files_are_the_committed_ones(repo: Path) -> None:
    assert get_pull_request_changed_files(repo, 'main') == [
        Path('.github/CODEOWNERS'),
        Path('added.txt'),
        Path('removed.txt'),
    ]


def test_changed_files_with_uncommitted_add_the_working_tree(repo: Path) -> None:
    assert get_pull_request_changed_files(repo, 'main', with_uncommitted=True) == [
        Path('.github/CODEOWNERS'),
        Path('added.txt'),
        Path('kept.txt'),
        Path('removed.txt'),
        Path('untracked.txt'),
    ]


@pytest.mark.parametrize('ref, owner', [('main', '@org/base'), ('HEAD', '@org/branch')])
def test_specifications_come_from_the_ref(repo: Path, ref: str, owner: str) -> None:
    write_file(repo, '.github/CODEOWNERS', '* @org/worktree\n')

    specifications = get_code_owner_specifications_at_ref(repo, ref)

    assert specifications is not None
    assert [spec.owners for spec in specifications] == [[owner]]
    assert specifications[0].codeowners_file_path == repo / '.github' / 'CODEOWNERS'


def test_specifications_follow_githubs_search_order(repo: Path) -> None:
    write_file(repo, 'CODEOWNERS', '* @org/root\n')
    write_file(repo, 'docs/CODEOWNERS', '* @org/docs\n')
    git(repo, 'rm', '-q', '.github/CODEOWNERS')
    commit_all(repo, 'move CODEOWNERS')

    specifications = get_code_owner_specifications_at_ref(repo, 'HEAD')

    assert specifications is not None
    assert specifications[0].owners == ['@org/root']


def test_specifications_are_none_without_a_codeowners_file(repo: Path) -> None:
    git(repo, 'rm', '-q', '.github/CODEOWNERS')
    commit_all(repo, 'drop CODEOWNERS')

    assert get_code_owner_specifications_at_ref(repo, 'HEAD') is None
    assert get_code_owner_specifications_at_ref(repo, 'no-such-ref') is None
