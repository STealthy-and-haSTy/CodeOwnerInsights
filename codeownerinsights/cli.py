import argparse
import json
import os
import sys
from pathlib import Path, PurePath
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, TextIO, Tuple

from .codeowners import (
    CodeOwnerSpecification,
    get_code_owners_file,
    get_matching_code_owner_specifications_for_file,
    parse_code_owners,
)
from .git import (
    DEFAULT_GIT,
    exec_command,
    get_default_branch_remote_ref,
    get_git_staged_files,
    get_git_unstaged_files,
)
from .pull_request import (
    PULL_REQUEST_DIFF_FILTER,
    get_code_owner_specifications_at_ref,
    get_pull_request_changed_files,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='codeownerinsights',
        description=(
            'Resolve the CODEOWNERS owners of files the way GitHub does. '
            'With no paths, use the files the current branch commits change compared with the '
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
        '--root-relative',
        action='store_true',
        help='paths, including those read from stdin, are relative to the repository root, as git prints them',
    )
    parser.add_argument(
        '-z',
        dest='null_separated',
        action='store_true',
        help="paths read from stdin are separated by NUL characters, as git's -z prints them",
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
        '--with-uncommitted',
        action='store_true',
        help=(
            'add uncommitted changes, untracked files included, to the branch changes: the files '
            'the pull request would change once everything is committed'
        ),
    )
    parser.add_argument(
        '--no-fetch',
        action='store_true',
        help='use the local origin/<default> ref without fetching it first',
    )
    codeowners_source = parser.add_mutually_exclusive_group()
    codeowners_source.add_argument(
        '--codeowners-ref',
        metavar='REF',
        help=(
            'read CODEOWNERS at this ref (default: the base for branch changes, as GitHub does; '
            'the working tree otherwise)'
        ),
    )
    codeowners_source.add_argument(
        '--worktree-codeowners',
        action='store_true',
        help='read CODEOWNERS from the working tree for branch changes too, to preview edits to it',
    )
    parser.add_argument(
        '--owner',
        action='append',
        default=[],
        help=(
            'only show files this owner covers; repeat for any of several. Case is ignored, and '
            '@ and the org are optional: core-banking matches @TransferGo/core-banking'
        ),
    )
    parser.add_argument(
        '--not-owner',
        action='append',
        default=[],
        help='leave out files this owner covers; repeat for several. Matches as --owner does',
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
    parser.add_argument(
        '--color',
        choices=('auto', 'always', 'never'),
        default='auto',
        help=(
            'colour text output: always, never, or auto (the default) when stdout is a terminal '
            'and NO_COLOR is not set'
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
    branch_only = [
        flag
        for flag, on in (
            ('--base', args.base),
            ('--no-fetch', args.no_fetch),
            ('--with-uncommitted', args.with_uncommitted),
        )
        if on
    ]
    if (args.root_relative or args.null_separated) and not args.paths:
        flag = '--root-relative' if args.root_relative else '-z'
        parser.error(f'{flag} needs paths')
    if args.null_separated and '-' not in args.paths:
        parser.error("-z needs '-' to read paths from stdin")
    if working_tree and args.paths:
        parser.error(f'{working_tree[0]} cannot be combined with paths')
    if branch_only and (working_tree or args.paths):
        other = working_tree[0] if working_tree else 'paths'
        parser.error(f'{branch_only[0]} cannot be combined with {other}')


def _is_branch_mode(args: argparse.Namespace) -> bool:
    return not (args.staged or args.unstaged or args.paths)


def _load_specifications(
    repo_root: Path, ref: Optional[str], git: str
) -> Optional[List[CodeOwnerSpecification]]:
    if ref is None:
        codeowners_file = get_code_owners_file(repo_root)
        if codeowners_file is None:
            return None
        return list(parse_code_owners(codeowners_file, codeowners_file.read_text(encoding='utf-8')))
    return get_code_owner_specifications_at_ref(repo_root, ref, git=git)


def _collect_paths(
    args: argparse.Namespace, cwd: Path, repo_root: Path, stdin: TextIO, base: Optional[str]
) -> List[Path]:
    changed: List[Path] = []
    if args.staged or args.unstaged:
        if args.staged:
            changed += get_git_staged_files(
                repo_root, git=args.git, diff_filter=PULL_REQUEST_DIFF_FILTER
            )
        if args.unstaged:
            changed += get_git_unstaged_files(
                repo_root, git=args.git, diff_filter=PULL_REQUEST_DIFF_FILTER
            )
        return sorted(set(changed))

    if args.paths:
        raw: List[str] = []
        for path in args.paths:
            if path == '-' and args.null_separated:
                raw.extend(entry for entry in stdin.read().split('\0') if entry)
            elif path == '-':
                raw.extend(line.strip() for line in stdin if line.strip())
            else:
                raw.append(path)
        relative_to = repo_root if args.root_relative else cwd
        return [_repo_relative(path, relative_to, repo_root) for path in raw]

    assert base is not None
    return get_pull_request_changed_files(
        repo_root, base, git=args.git, with_uncommitted=args.with_uncommitted
    )


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


def _owner_matches(wanted: str, owner: str) -> bool:
    wanted = wanted.lower().lstrip('@')
    owner = owner.lower().lstrip('@')
    return wanted == owner or ('/' not in wanted and owner.endswith(f'/{wanted}'))


def _covered_by_any(result: Dict[str, object], wanted: Sequence[str]) -> bool:
    return any(
        _owner_matches(w, owner)
        for w in wanted
        for owner in result['owners']  # type: ignore[union-attr]
    )


def _filter_by_owner(
    results: List[Dict[str, object]], owner: Sequence[str], not_owner: Sequence[str]
) -> List[Dict[str, object]]:
    return [
        result
        for result in results
        if (not owner or _covered_by_any(result, owner))
        and not (not_owner and _covered_by_any(result, not_owner))
    ]


def _owners_summary(results: List[Dict[str, object]]) -> Dict[str, List[str]]:
    summary: Dict[str, List[str]] = {}
    for result in results:
        for owner in result['owners']:  # type: ignore[union-attr]
            summary.setdefault(owner, []).append(result['path'])  # type: ignore[arg-type]
    return dict(sorted(summary.items()))


def _describe_rule(rule: Dict[str, object]) -> str:
    return f'{rule["codeowners_file"]}:{rule["line"]} {rule["pattern"]}'


class _Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f'\033[{code}m{text}\033[0m' if self.enabled and text else text

    def owners(self, text: str) -> str:
        return self._wrap('1;36', text)

    def rule(self, text: str) -> str:
        return self._wrap('2', text)

    def unowned(self, text: str) -> str:
        return self._wrap('33', text)

    def heading(self, text: str) -> str:
        return self._wrap('1', text)


def _use_color(choice: str, stdout: TextIO, environ: Mapping[str, str]) -> bool:
    if choice != 'auto':
        return choice == 'always'
    isatty = getattr(stdout, 'isatty', None)
    return bool(isatty and isatty()) and not environ.get('NO_COLOR')


def _files(count: int) -> str:
    return f'{count} file{"s" if count != 1 else ""}'


def _print_matching_rules(
    result: Dict[str, object], indent: str, style: _Style, out: TextIO
) -> None:
    for matching in result['matching_rules']:  # type: ignore[union-attr]
        line = f'{_describe_rule(matching)} -> {" ".join(matching["owners"])}'
        if matching == result['rule']:
            out.write(f'{indent}* {line}\n')
        else:
            out.write(f'{indent}  {style.rule(line)}\n')


def _print_text(
    results: List[Dict[str, object]], all_rules: bool, style: _Style, out: TextIO
) -> None:
    for result in results:
        rule = result['rule']
        if rule is None:
            out.write(f'{result["path"]}\t{style.unowned("(no owner)")}\n')
        else:
            owners = style.owners(' '.join(result['owners']))  # type: ignore[arg-type]
            out.write(f'{result["path"]}\t{owners}\t{style.rule(_describe_rule(rule))}\n')  # type: ignore[arg-type]
        if all_rules:
            _print_matching_rules(result, '  ', style, out)

    summary = _owners_summary(results)
    if summary:
        out.write(f'\n{style.heading("Owners:")}\n')
        for owner, paths in summary.items():
            out.write(f'  {style.owners(owner)} ({_files(len(paths))})\n')
    unowned = [result['path'] for result in results if result['rule'] is None]
    if unowned:
        out.write(f'\n{style.unowned("No owner:")} {_files(len(unowned))}\n')


def _print_text_by_owner(
    results: List[Dict[str, object]], all_rules: bool, style: _Style, out: TextIO
) -> None:
    groups: Dict[Tuple[str, ...], List[Dict[str, object]]] = {}
    for result in results:
        groups.setdefault(tuple(result['owners']), []).append(result)  # type: ignore[arg-type]
    width = max(len(str(result['path'])) for result in results)

    for index, owners in enumerate(sorted(groups, key=lambda owners: (not owners, owners))):
        members = groups[owners]
        heading = style.owners(' '.join(owners)) if owners else style.unowned('(no owner)')
        if index:
            out.write('\n')
        out.write(f'{heading} ({_files(len(members))})\n')
        for result in members:
            rule = result['rule']
            if rule is None:
                out.write(f'  {result["path"]}\n')
            else:
                path = f'{str(result["path"]):<{width}}'
                out.write(f'  {path}  {style.rule(_describe_rule(rule))}\n')  # type: ignore[arg-type]
            if all_rules:
                _print_matching_rules(result, '    ', style, out)


def main(
    argv: Optional[Sequence[str]] = None,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    cwd: Optional[Path] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _check_sources(parser, args)
    cwd = (cwd or Path.cwd()).resolve()
    repo_root = (args.repo if args.repo.is_absolute() else cwd / args.repo) if args.repo else None
    repo_root = (repo_root or _find_repo_root(cwd, args.git)).resolve()

    def fail(message: str, code: int) -> int:
        if args.json:
            json.dump({'error': message}, stderr)
            stderr.write('\n')
        else:
            stderr.write(f'{message}\n')
        return code

    base: Optional[str] = None
    if _is_branch_mode(args):
        base = args.base or get_default_branch_remote_ref(
            repo_root, fetch_remote=not args.no_fetch, git=args.git
        )
        if not base:
            return fail('Could not find the default branch from origin/HEAD; pass --base <ref>', 1)

    codeowners_ref = args.codeowners_ref
    if codeowners_ref is None and base and not args.worktree_codeowners:
        codeowners_ref = base

    specifications = _load_specifications(repo_root, codeowners_ref, args.git)
    if specifications is None:
        if codeowners_ref is None:
            return fail(f'No CODEOWNERS file found in {repo_root}', 2)
        message = f'No CODEOWNERS file found at {codeowners_ref}'
        if not args.codeowners_ref:
            message += (
                ". GitHub requests code owners from the base branch's CODEOWNERS file; "
                "pass --worktree-codeowners to use the working tree's instead"
            )
        return fail(message, 2)

    results = _resolve(
        specifications, _collect_paths(args, cwd, repo_root, stdin, base), repo_root, args.all_rules
    )
    filtered = bool(results) and bool(args.owner or args.not_owner)
    results = _filter_by_owner(results, args.owner, args.not_owner)

    if args.json:
        json.dump(
            {
                'files': results,
                'owners': _owners_summary(results),
                'codeowners_ref': codeowners_ref,
            },
            stdout,
            indent=2,
        )
        stdout.write('\n')
    elif results:
        style = _Style(_use_color(args.color, stdout, os.environ if environ is None else environ))
        printer = _print_text_by_owner if args.group_by == 'owner' else _print_text
        printer(results, args.all_rules, style, stdout)
        if codeowners_ref:
            stdout.write(f'\n{style.rule(f"CODEOWNERS at {codeowners_ref}")}\n')
    elif filtered:
        stderr.write('No files match --owner or --not-owner\n')
    else:
        stderr.write('No files to resolve\n')
    return 0
