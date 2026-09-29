from pathlib import Path
from typing import Iterable, Optional, Tuple
import sys
import subprocess
from subprocess import run, PIPE
import time
from dataclasses import dataclass


@dataclass
class ShellExecutionSummary:
    process: Optional[subprocess.CompletedProcess]
    time_taken: float


def get_git_changed_files_compared_to_branch(
    folder_path: Path, base_branch_name: str, filter: Optional[str] = None
) -> Iterable[Path]:
    """filter can be like --relative=source/ or '*.php' etc."""
    current_branch = get_current_branch(folder_path)
    if not current_branch:
        return []
    # find the common ancestor incase local or remote base branch is more up to date than the feature branch
    merge_base = exec_command(
        folder_path, ["git", "merge-base", base_branch_name, current_branch]
    )
    if not merge_base or merge_base.process.returncode != 0:
        return []
    diff_cmd = [
        "git",
        "diff",
        merge_base.process.stdout.rstrip(),
        "--name-only",
        "--diff-filter=ACMR",
    ]
    if filter:
        diff_cmd.append(filter)
    files = exec_command(folder_path, diff_cmd)
    if not files:
        return []
    return (
        Path(file) for file in files.process.stdout.split("\n") if file
    )  # purists would say that files can be named with \n chars...


def get_git_changed_files_compared_to_default_branch(
    folder_path: Path, filter: Optional[str] = None
) -> Iterable[Path]:
    """filter can be like --relative=source/ or '*.php' etc."""
    # https://stackoverflow.com/q/28666357/4473405
    default_branch = get_default_branch(folder_path)
    if not default_branch:
        return []
    return get_git_changed_files_compared_to_branch(folder_path, default_branch, filter)


def get_default_branch(folder_path: Path) -> Optional[str]:
    result = exec_command(
        folder_path, ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"]
    )
    if result and result.process.returncode == 0:
        # origin/HEAD points to something like 'origin/main' - extract the branch name
        ref = result.process.stdout.rstrip()
        if ref.startswith("origin/"):
            return ref[len("origin/") :]
        return ref
    return None


def get_current_branch(folder_path: Path) -> Optional[str]:
    result = exec_command(folder_path, ["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if result and result.process.returncode == 0:
        return result.process.stdout.rstrip()
    return None


def exec_command(folder_path: Path, cmd: list[str]) -> ShellExecutionSummary:
    return execute_with_stdin(cmd, False, "", folder_path)


# returns the completed subpress and how long it took to complete as a float
def execute_with_stdin(
    cmd, shell, text, cwd: Optional[Path] = None
) -> ShellExecutionSummary:
    before = time.perf_counter()
    # https://docs.python.org/3/library/subprocess.html#subprocess.run - new in version 3.5
    # therefore, you need to be using ST build >= 4050 and the package should be opting in to Python 3.8 plugin host
    p = run(
        cmd, shell=shell, capture_output=True, input=text, encoding="utf-8", cwd=cwd
    )
    after = time.perf_counter()
    return ShellExecutionSummary(p, after - before)
