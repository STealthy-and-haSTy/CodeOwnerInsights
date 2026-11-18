import io
import json
import subprocess
import sys
from pathlib import Path, PureWindowsPath
from typing import List, Optional, Tuple

import pytest

from codeownerinsights import cli
from codeownerinsights.codeowners import CodeOwnerSpecification

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
    code = cli.main(args, stdin=io.StringIO(stdin), stdout=out, stderr=err, cwd=cwd)
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
    rule = result['files'][0]['rule']
    assert rule == {
        'pattern': '/docs/',
        'owners': ['@org/docs'],
        'line': 6,
        'codeowners_file': '.github/CODEOWNERS',
    }
    assert '\\' not in rule['codeowners_file']
    assert 'matching_rules' not in result['files'][0]


def test_json_output_all_rules(folder: Path) -> None:
    code, out, _ = run_cli(['--repo', '.', '--json', '--all-rules', 'docs/a.md'], cwd=folder)

    assert code == 0
    result = json.loads(out)
    assert len(result['files'][0]['matching_rules']) == 2
    for matching in result['files'][0]['matching_rules']:
        assert '\\' not in matching['codeowners_file']


def windows_relative_to_repo(path: Path, start: Path) -> PureWindowsPath:
    return PureWindowsPath(r'.github\CODEOWNERS')


def test_rule_dict_normalizes_windows_separators(tmp_path: Path, monkeypatch) -> None:
    spec = CodeOwnerSpecification(
        line_number=1,
        glob_pattern='*',
        owners=['@org/everyone'],
        codeowners_file_path=tmp_path / '.github' / 'CODEOWNERS',
        nearest_comment=None,
    )

    monkeypatch.setattr(cli, '_relative_to_repo', windows_relative_to_repo)

    assert cli._rule_dict(spec, tmp_path)['codeowners_file'] == '.github/CODEOWNERS'


def test_fails_without_a_codeowners_file(tmp_path: Path) -> None:
    code, out, err = run_cli(['--repo', '.', 'src/app.py'], cwd=tmp_path)

    assert code == 2
    assert out == ''
    assert err == f'No CODEOWNERS file found in {tmp_path.resolve()}\n'


def test_fails_without_a_codeowners_file_as_json(tmp_path: Path) -> None:
    code, _, err = run_cli(['--repo', '.', '--json', 'src/app.py'], cwd=tmp_path)

    assert code == 2
    assert err.endswith('}\n')
    assert 'No CODEOWNERS file found' in json.loads(err)['error']


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


@pytest.fixture
def working_tree(repo: Path) -> Path:
    write_file(repo, '.gitignore', 'build/\n')
    commit_all(repo, 'ignore build output')
    write_file(repo, 'docs/staged.md', '# staged\n')
    git(repo, 'add', 'docs/staged.md')
    write_file(repo, 'src/kept.py', '# edited\n')
    write_file(repo, 'source/app/Identity/Added.php', '<?php // edited\n')
    git(repo, 'rm', '--cached', '-q', 'source/app/Identity/Added.php')
    write_file(repo, 'notes/untracked.txt', 'new\n')
    write_file(repo, 'build/ignored.txt', 'ignored\n')
    return repo


def changed_paths(out: str) -> List[str]:
    return [file['path'] for file in json.loads(out)['files']]


@pytest.mark.skipif(sys.platform == 'win32', reason='the git helpers shell out to bash')
def test_staged_resolves_the_index_changes_including_deletions(working_tree: Path) -> None:
    code, out, _ = run_cli(['--json', '--staged'], cwd=working_tree / 'src')

    assert code == 0
    assert changed_paths(out) == ['docs/staged.md', 'source/app/Identity/Added.php']


@pytest.mark.skipif(sys.platform == 'win32', reason='the git helpers shell out to bash')
def test_unstaged_resolves_working_tree_and_untracked_files(working_tree: Path) -> None:
    code, out, _ = run_cli(['--json', '--unstaged'], cwd=working_tree / 'src')

    assert code == 0
    assert changed_paths(out) == [
        'notes/untracked.txt',
        'source/app/Identity/Added.php',
        'src/kept.py',
    ]


@pytest.mark.skipif(sys.platform == 'win32', reason='the git helpers shell out to bash')
def test_staged_and_unstaged_together_list_each_file_once(working_tree: Path) -> None:
    code, out, _ = run_cli(['--json', '--staged', '--unstaged'], cwd=working_tree)

    assert code == 0
    assert changed_paths(out) == [
        'docs/staged.md',
        'notes/untracked.txt',
        'source/app/Identity/Added.php',
        'src/kept.py',
    ]


@pytest.mark.parametrize(
    'args, message',
    [
        (['--staged', 'src/app.py'], '--staged cannot be combined with paths'),
        (['--unstaged', '-'], '--unstaged cannot be combined with paths'),
        (['--staged', '--base', 'main'], '--base cannot be combined with --staged'),
        (['--unstaged', '--no-fetch'], '--no-fetch cannot be combined with --unstaged'),
        (['--with-uncommitted', '--staged'], '--with-uncommitted cannot be combined with --staged'),
        (['--with-uncommitted', 'src/app.py'], '--with-uncommitted cannot be combined with paths'),
        (['--base', 'main', 'src/app.py'], '--base cannot be combined with paths'),
    ],
)
def test_rejects_flags_that_pick_different_files(
    folder: Path, capsys, args: List[str], message: str
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        run_cli(['--repo', '.'] + args, cwd=folder)

    assert exit_info.value.code == 2
    assert capsys.readouterr().err.endswith(f'error: {message}\n')


@pytest.mark.skipif(sys.platform == 'win32', reason='the git helpers shell out to bash')
def test_says_so_when_there_are_no_files(repo: Path) -> None:
    code, out, err = run_cli(['--staged'], cwd=repo)

    assert code == 0
    assert out == ''
    assert err == 'No files to resolve\n'


def test_group_by_owner_lists_files_under_each_owner_set(tmp_path: Path) -> None:
    write_file(tmp_path, 'CODEOWNERS', '* @org/everyone\n/docs/ @org/docs @org/writers\n/vendor/\n')

    code, out, _ = run_cli(
        [
            '--repo',
            '.',
            '--group-by',
            'owner',
            'vendor/lib.py',
            'docs/a.md',
            'src/app.py',
            'docs/b.md',
        ],
        cwd=tmp_path,
    )

    assert code == 0
    assert out.splitlines() == [
        '@org/docs @org/writers (2 files)',
        '  docs/a.md      CODEOWNERS:2 /docs/',
        '  docs/b.md      CODEOWNERS:2 /docs/',
        '',
        '@org/everyone (1 file)',
        '  src/app.py     CODEOWNERS:1 *',
        '',
        '(no owner) (1 file)',
        '  vendor/lib.py  CODEOWNERS:3 /vendor/',
    ]


def test_group_by_owner_with_all_rules(folder: Path) -> None:
    code, out, _ = run_cli(
        ['--repo', '.', '--group-by', 'owner', '--all-rules', 'docs/a.md'], cwd=folder
    )

    assert code == 0
    assert out.splitlines() == [
        '@org/docs (1 file)',
        '  docs/a.md  .github/CODEOWNERS:6 /docs/',
        '      .github/CODEOWNERS:1 * -> @org/everyone',
        '    * .github/CODEOWNERS:6 /docs/ -> @org/docs',
    ]


def test_group_by_owner_leaves_json_unchanged(folder: Path) -> None:
    _, grouped, _ = run_cli(
        ['--repo', '.', '--json', '--group-by', 'owner', 'docs/a.md'], cwd=folder
    )
    _, plain, _ = run_cli(['--repo', '.', '--json', 'docs/a.md'], cwd=folder)

    assert grouped == plain


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def run_cli_on(out: io.StringIO, args: List[str], cwd: Path, environ: Optional[dict] = None) -> str:
    cli.main(
        args, stdin=io.StringIO(), stdout=out, stderr=io.StringIO(), cwd=cwd, environ=environ or {}
    )
    return out.getvalue()


@pytest.mark.parametrize(
    'stdout, color, environ, coloured',
    [
        (Terminal, 'auto', {}, True),
        (Terminal, 'auto', {'NO_COLOR': '1'}, False),
        (Terminal, 'auto', {'NO_COLOR': ''}, True),
        (Terminal, 'never', {}, False),
        (io.StringIO, 'auto', {}, False),
        (io.StringIO, 'always', {'NO_COLOR': '1'}, True),
    ],
)
@pytest.mark.parametrize('group_by', ['file', 'owner'])
def test_colour_choice(
    folder: Path, stdout, color: str, environ: dict, coloured: bool, group_by: str
) -> None:
    out = run_cli_on(
        stdout(),
        ['--repo', '.', '--color', color, '--group-by', group_by, 'docs/a.md'],
        folder,
        environ,
    )

    assert ('\033[' in out) is coloured


def test_colour_styles_owners_and_rules(folder: Path) -> None:
    out = run_cli_on(io.StringIO(), ['--repo', '.', '--color', 'always', 'docs/a.md'], folder)

    assert out.splitlines()[0] == (
        'docs/a.md\t\033[1;36m@org/docs\033[0m\t\033[2m.github/CODEOWNERS:6 /docs/\033[0m'
    )


def test_colour_keeps_grouped_rules_aligned(folder: Path) -> None:
    out = run_cli_on(
        io.StringIO(),
        ['--repo', '.', '--color', 'always', '--group-by', 'owner', 'docs/a.md', 'docs/longer.md'],
        folder,
    )

    assert out.splitlines()[1:3] == [
        '  docs/a.md       \033[2m.github/CODEOWNERS:6 /docs/\033[0m',
        '  docs/longer.md  \033[2m.github/CODEOWNERS:6 /docs/\033[0m',
    ]


def test_json_is_never_coloured(folder: Path) -> None:
    out = run_cli_on(
        Terminal(), ['--repo', '.', '--json', '--color', 'always', 'docs/a.md'], folder
    )

    assert '\033[' not in out


@pytest.fixture
def uncommitted_branch(repo: Path) -> Path:
    write_file(repo, 'src/kept.py', '# edited, not committed\n')
    write_file(repo, 'docs/staged.md', '# staged\n')
    git(repo, 'add', 'docs/staged.md')
    write_file(repo, 'notes/untracked.txt', 'new\n')
    return repo


@pytest.mark.skipif(sys.platform == 'win32', reason='the git helpers shell out to bash')
def test_branch_changes_leave_out_uncommitted_changes(uncommitted_branch: Path) -> None:
    code, out, _ = run_cli(['--json', '--no-fetch'], cwd=uncommitted_branch)

    assert code == 0
    assert changed_paths(out) == ['docs/removed.md', 'source/app/Identity/Added.php']


@pytest.mark.skipif(sys.platform == 'win32', reason='the git helpers shell out to bash')
def test_with_uncommitted_adds_the_working_tree_and_untracked_files(
    uncommitted_branch: Path,
) -> None:
    code, out, _ = run_cli(
        ['--json', '--no-fetch', '--with-uncommitted'], cwd=uncommitted_branch / 'src'
    )

    assert code == 0
    assert changed_paths(out) == [
        'docs/removed.md',
        'docs/staged.md',
        'notes/untracked.txt',
        'source/app/Identity/Added.php',
        'src/kept.py',
    ]
