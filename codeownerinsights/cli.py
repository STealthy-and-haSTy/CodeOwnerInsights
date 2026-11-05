import argparse
import json
import os
import sys
from pathlib import Path, PurePath
from typing import Dict, Iterable, List, Optional, Sequence, TextIO

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


def _collect_paths(
    args: argparse.Namespace, cwd: Path, repo_root: Path, stdin: TextIO
) -> List[Path]:
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


def _print_text(results: List[Dict[str, object]], all_rules: bool, out: TextIO) -> None:
    for result in results:
        rule = result['rule']
        if rule is None:
            out.write(f'{result["path"]}\t(no owner)\n')
        else:
            owners = ' '.join(result['owners'])  # type: ignore[arg-type]
            out.write(f'{result["path"]}\t{owners}\t{_describe_rule(rule)}\n')  # type: ignore[arg-type]
        if all_rules:
            for matching in result['matching_rules']:  # type: ignore[union-attr]
                marker = '*' if matching == rule else ' '
                owners = ' '.join(matching['owners'])
                out.write(f'  {marker} {_describe_rule(matching)} -> {owners}\n')

    summary = _owners_summary(results)
    if summary:
        out.write('\nOwners:\n')
        for owner, paths in summary.items():
            out.write(f'  {owner} ({len(paths)} file{"s" if len(paths) != 1 else ""})\n')
    unowned = [result['path'] for result in results if result['rule'] is None]
    if unowned:
        out.write(f'\nNo owner: {len(unowned)} file{"s" if len(unowned) != 1 else ""}\n')


def main(
    argv: Optional[Sequence[str]] = None,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    cwd: Optional[Path] = None,
) -> int:
    args = _build_parser().parse_args(argv)
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
    else:
        _print_text(results, args.all_rules, stdout)
    return 0
