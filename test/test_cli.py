import io
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

from codeownerinsights.cli import main

CODEOWNERS = """\
* @org/everyone

# Identity
source/**/Identity/ @org/identity

/docs/ @org/docs
"""


def write_file(folder: Path, relative_path: str, content: str) -> Path:
    path = folder / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return path


def run_cli(args: List[str], cwd: Path, stdin: str = '') -> Tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(args, stdin=io.StringIO(stdin), stdout=out, stderr=err, cwd=cwd)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    write_file(tmp_path, '.github/CODEOWNERS', CODEOWNERS)
    return tmp_path


def test_resolves_the_last_matching_rule_for_each_path(folder: Path) -> None:
    code, out, _ = run_cli(
        ['--repo', '.', 'src/app.py', 'source/src/Model/Identity/User.php'], cwd=folder
    )

    assert code == 0
    lines = out.splitlines()
    assert lines[0] == 'src/app.py\t@org/everyone\t.github/CODEOWNERS:1 *'
    assert lines[1] == (
        'source/src/Model/Identity/User.php\t@org/identity\t.github/CODEOWNERS:4 source/**/Identity/'
    )
    assert '  @org/everyone (1 file)' in lines
    assert '  @org/identity (1 file)' in lines


def test_paths_are_relative_to_the_working_directory(folder: Path) -> None:
    code, out, _ = run_cli(['--repo', '..', 'guide.md'], cwd=folder / 'docs')

    assert code == 0
    assert out.splitlines()[0] == 'docs/guide.md\t@org/docs\t.github/CODEOWNERS:6 /docs/'


def test_reads_paths_from_stdin(folder: Path) -> None:
    code, out, _ = run_cli(['--repo', '.', '-'], cwd=folder, stdin='docs/a.md\n\nsrc/b.py\n')

    assert code == 0
    assert [line.split('\t')[0] for line in out.splitlines()[:2]] == ['docs/a.md', 'src/b.py']


def test_all_rules_marks_the_rule_that_applies(folder: Path) -> None:
    code, out, _ = run_cli(['--repo', '.', '--all-rules', 'docs/a.md'], cwd=folder)

    assert code == 0
    assert out.splitlines()[1:3] == [
        '    .github/CODEOWNERS:1 * -> @org/everyone',
        '  * .github/CODEOWNERS:6 /docs/ -> @org/docs',
    ]


def test_reports_files_without_an_owner(tmp_path: Path) -> None:
    write_file(tmp_path, 'CODEOWNERS', '/docs/ @org/docs\n')

    code, out, _ = run_cli(['--repo', '.', 'src/app.py'], cwd=tmp_path)

    assert code == 0
    assert out.splitlines()[0] == 'src/app.py\t(no owner)'
    assert 'No owner: 1 file' in out


def test_json_output(folder: Path) -> None:
    code, out, _ = run_cli(['--repo', '.', '--json', 'docs/a.md'], cwd=folder)

    assert code == 0
    result = json.loads(out)
    assert result['owners'] == {'@org/docs': ['docs/a.md']}
    assert result['files'][0]['rule'] == {
        'pattern': '/docs/',
        'owners': ['@org/docs'],
        'line': 6,
        'codeowners_file': '.github/CODEOWNERS',
    }
    assert 'matching_rules' not in result['files'][0]


def test_json_output_all_rules(folder: Path) -> None:
    code, out, _ = run_cli(['--repo', '.', '--json', '--all-rules', 'docs/a.md'], cwd=folder)

    assert code == 0
    result = json.loads(out)
    assert len(result['files'][0]['matching_rules']) == 2


def test_fails_without_a_codeowners_file(tmp_path: Path) -> None:
    code, out, err = run_cli(['--repo', '.', 'src/app.py'], cwd=tmp_path)

    assert code == 2
    assert out == ''
    assert 'No CODEOWNERS file found' in err


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ['git', *args], cwd=str(cwd), check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def commit_all(folder: Path, message: str) -> None:
    git(folder, 'add', '-A')
    git(folder, 'commit', '-m', message, '--no-gpg-sign')


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    origin = tmp_path / 'origin.git'
    origin.mkdir()
    git(tmp_path, 'init', '--bare', '--initial-branch=main', str(origin))

    folder = tmp_path / 'repo'
    folder.mkdir()
    git(folder, 'init', '--initial-branch=main')
    git(folder, 'config', 'user.name', 'CodeOwnerInsights')
    git(folder, 'config', 'user.email', 'test@example.com')
    git(folder, 'config', 'commit.gpgsign', 'false')

    write_file(folder, 'CODEOWNERS', CODEOWNERS)
    write_file(folder, 'docs/removed.md', '# removed\n')
    write_file(folder, 'src/kept.py', '# kept\n')
    commit_all(folder, 'initial commit')
    git(folder, 'remote', 'add', 'origin', str(origin))
    git(folder, 'push', '--set-upstream', 'origin', 'main')
    git(folder, 'remote', 'set-head', 'origin', 'main')

    git(folder, 'checkout', '-b', 'feature')
    write_file(folder, 'source/app/Identity/Added.php', '<?php\n')
    (folder / 'docs' / 'removed.md').unlink()
    commit_all(folder, 'feature changes')

    return folder


@pytest.mark.skipif(sys.platform == 'win32', reason='the git helpers shell out to bash')
@pytest.mark.parametrize('base', [None, 'main'])
def test_without_paths_resolves_the_branch_changes_including_deletions(
    repo: Path, base: Optional[str]
) -> None:
    args = ['--json', '--no-fetch'] + (['--base', base] if base else [])

    code, out, _ = run_cli(args, cwd=repo / 'src')

    assert code == 0
    assert json.loads(out)['owners'] == {
        '@org/docs': ['docs/removed.md'],
        '@org/identity': ['source/app/Identity/Added.php'],
    }
