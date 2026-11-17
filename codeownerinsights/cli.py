import argparse
import json
import os
import sys
from pathlib import Path, PurePath
from typing import Dict, Iterable, List, Optional, Sequence, TextIO, Tuple

from .codeowners import (
    CodeOwnerSpecification,
    get_code_owners_file,
    get_matching_code_owner_specifications_for_file,
    parse_code_owners,
)
from .git import (
    DEFAULT_GIT,
    exec_command,
    get_git_changed_files_compared_to_branch,
    get_git_changed_files_compared_to_default_branch,
    get_git_staged_files,
    get_git_unstaged_files,
)

PR_DIFF_FILTER = 'ACMRD'


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='codeownerinsights',
        description=(
            'Resolve the CODEOWNERS owners of files the way GitHub does. '
            'With no paths, use the files the current branch changes compared with the '
            "default branch, which are the files GitHub requests a pull request's reviewers for."
        ),
    )
    parser.add_argument(
        '--staged',
        action='store_true',
        help='use the files changed in the index instead of the branch changes',
    )
    parser.add_argument(
        '--unstaged',
        action='store_true',
        help=(
            'use the files changed in the working tree, and untracked files, instead of the '
            'branch changes; combine with --staged for every uncommitted change'
        ),
    )
    parser.add_argument(
        'paths',
        nargs='*',
        help="files to resolve, relative to the current directory; '-' reads paths from stdin",
    )
    parser.add_argument(
        '--repo',
        type=Path,
        help='repository root (default: the git top level of the current directory)',
    )
    parser.add_argument(
        '--base',
        help='compare the current branch with this ref instead of the default branch',
    )
    parser.add_argument(
        '--no-fetch',
        action='store_true',
        help='use the local origin/<default> ref without fetching it first',
    )
    parser.add_argument(
        '--all-rules',
        action='store_true',
        help='also list every rule that matches each file, not only the one that applies',
    )
    parser.add_argument(
        '--group-by',
        choices=('file', 'owner'),
        default='file',
        help=(
            'text output only: list one file per line (file, the default), or list the files '
            'under each set of owners that applies to them (owner)'
        ),
    )
    parser.add_argument('--json', action='store_true', help='print JSON instead of text')
    parser.add_argument('--git', default=DEFAULT_GIT, help='git executable (default: git)')
    return parser


def _find_repo_root(start: Path, git: str) -> Path:
    result = exec_command(start, [git, 'rev-parse', '--show-toplevel'])
    if result and result.process.returncode == 0 and result.process.stdout.strip():
        return Path(result.process.stdout.strip())
    return start


def _repo_relative(path: str, cwd: Path, repo_root: Path) -> Path:
    absolute = Path(path) if os.path.isabs(path) else cwd / path
    return Path(os.path.relpath(os.path.normpath(str(absolute)), str(repo_root)))


def _check_sources(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    working_tree = [
        flag for flag, on in (('--staged', args.staged), ('--unstaged', args.unstaged)) if on
    ]
    if not working_tree:
        return
    if args.paths:
        parser.error(f'{working_tree[0]} cannot be combined with paths')
    if args.base or args.no_fetch:
        other = '--base' if args.base else '--no-fetch'
        parser.error(f'{working_tree[0]} cannot be combined with {other}')


def _collect_paths(
    args: argparse.Namespace, cwd: Path, repo_root: Path, stdin: TextIO
) -> List[Path]:
    if args.staged or args.unstaged:
        changed: List[Path] = []
        if args.staged:
            changed += get_git_staged_files(repo_root, git=args.git, diff_filter=PR_DIFF_FILTER)
        if args.unstaged:
            changed += get_git_unstaged_files(repo_root, git=args.git, diff_filter=PR_DIFF_FILTER)
        return sorted(set(changed))

    if args.paths:
        raw: List[str] = []
        for path in args.paths:
            if path == '-':
                raw.extend(line.strip() for line in stdin if line.strip())
            else:
                raw.append(path)
        return [_repo_relative(path, cwd, repo_root) for path in raw]

    if args.base:
        changed = get_git_changed_files_compared_to_branch(
            repo_root, args.base, git=args.git, diff_filter=PR_DIFF_FILTER
        )
    else:
        changed = get_git_changed_files_compared_to_default_branch(
            repo_root, fetch_remote=not args.no_fetch, git=args.git, diff_filter=PR_DIFF_FILTER
        )
    return list(changed)


def _relative_to_repo(path: Path, repo_root: Path) -> PurePath:
    return PurePath(os.path.relpath(str(path), str(repo_root)))


def _rule_dict(spec: CodeOwnerSpecification, repo_root: Path) -> Dict[str, object]:
    return {
        'pattern': spec.glob_pattern,
        'owners': list(spec.owners),
        'line': spec.line_number,
        'codeowners_file': _relative_to_repo(spec.codeowners_file_path, repo_root).as_posix(),
    }


def _resolve(
    specifications: Sequence[CodeOwnerSpecification],
    paths: Iterable[Path],
    repo_root: Path,
    all_rules: bool = False,
) -> List[Dict[str, object]]:
    results = []
    for path in paths:
        matching = list(get_matching_code_owner_specifications_for_file(specifications, path))
        applied = matching[-1] if matching else None
        result = {
            'path': path.as_posix(),
            'owners': list(applied.owners) if applied else [],
            'rule': _rule_dict(applied, repo_root) if applied else None,
        }
        if all_rules:
            result['matching_rules'] = [_rule_dict(spec, repo_root) for spec in matching]
        results.append(result)
    return results


def _owners_summary(results: List[Dict[str, object]]) -> Dict[str, List[str]]:
    summary: Dict[str, List[str]] = {}
    for result in results:
        for owner in result['owners']:  # type: ignore[union-attr]
            summary.setdefault(owner, []).append(result['path'])  # type: ignore[arg-type]
    return dict(sorted(summary.items()))


def _describe_rule(rule: Dict[str, object]) -> str:
    return f'{rule["codeowners_file"]}:{rule["line"]} {rule["pattern"]}'


def _files(count: int) -> str:
    return f'{count} file{"s" if count != 1 else ""}'


def _print_matching_rules(result: Dict[str, object], indent: str, out: TextIO) -> None:
    for matching in result['matching_rules']:  # type: ignore[union-attr]
        marker = '*' if matching == result['rule'] else ' '
        owners = ' '.join(matching['owners'])
        out.write(f'{indent}{marker} {_describe_rule(matching)} -> {owners}\n')


def _print_text(results: List[Dict[str, object]], all_rules: bool, out: TextIO) -> None:
    for result in results:
        rule = result['rule']
        if rule is None:
            out.write(f'{result["path"]}\t(no owner)\n')
        else:
            owners = ' '.join(result['owners'])  # type: ignore[arg-type]
            out.write(f'{result["path"]}\t{owners}\t{_describe_rule(rule)}\n')  # type: ignore[arg-type]
        if all_rules:
            _print_matching_rules(result, '  ', out)

    summary = _owners_summary(results)
    if summary:
        out.write('\nOwners:\n')
        for owner, paths in summary.items():
            out.write(f'  {owner} ({_files(len(paths))})\n')
    unowned = [result['path'] for result in results if result['rule'] is None]
    if unowned:
        out.write(f'\nNo owner: {_files(len(unowned))}\n')


def _print_text_by_owner(results: List[Dict[str, object]], all_rules: bool, out: TextIO) -> None:
    groups: Dict[Tuple[str, ...], List[Dict[str, object]]] = {}
    for result in results:
        groups.setdefault(tuple(result['owners']), []).append(result)  # type: ignore[arg-type]
    width = max(len(str(result['path'])) for result in results)

    for index, owners in enumerate(sorted(groups, key=lambda owners: (not owners, owners))):
        members = groups[owners]
        heading = ' '.join(owners) if owners else '(no owner)'
        if index:
            out.write('\n')
        out.write(f'{heading} ({_files(len(members))})\n')
        for result in members:
            rule = result['rule']
            if rule is None:
                out.write(f'  {result["path"]}\n')
            else:
                out.write(f'  {str(result["path"]):<{width}}  {_describe_rule(rule)}\n')  # type: ignore[arg-type]
            if all_rules:
                _print_matching_rules(result, '    ', out)


def main(
    argv: Optional[Sequence[str]] = None,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    cwd: Optional[Path] = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _check_sources(parser, args)
    cwd = (cwd or Path.cwd()).resolve()
    repo_root = (args.repo if args.repo.is_absolute() else cwd / args.repo) if args.repo else None
    repo_root = (repo_root or _find_repo_root(cwd, args.git)).resolve()

    codeowners_file = get_code_owners_file(repo_root)
    if codeowners_file is None:
        message = f'No CODEOWNERS file found in {repo_root}'
        if args.json:
            json.dump({'error': message}, stderr)
            stderr.write('\n')
        else:
            stderr.write(f'{message}\n')
        return 2

    specifications = list(
        parse_code_owners(codeowners_file, codeowners_file.read_text(encoding='utf-8'))
    )
    results = _resolve(
        specifications, _collect_paths(args, cwd, repo_root, stdin), repo_root, args.all_rules
    )

    if args.json:
        json.dump({'files': results, 'owners': _owners_summary(results)}, stdout, indent=2)
        stdout.write('\n')
    elif results and args.group_by == 'owner':
        _print_text_by_owner(results, args.all_rules, stdout)
    elif results:
        _print_text(results, args.all_rules, stdout)
    else:
        stderr.write('No files to resolve\n')
    return 0
