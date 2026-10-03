from pathlib import Path
from typing import Iterable, List, Optional, Tuple
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
    # Compare against the remote-tracking ref for the default branch (e.g.
    # origin/main), which is the real baseline for a PR. The local default
    # branch is frequently stale, and comparing against it would drag the merge
    # base back and surface unrelated default-branch commits.
    base_branch_name = get_default_branch_remote_ref(folder_path)
    if not base_branch_name:
        return []
    return get_git_changed_files_compared_to_branch(folder_path, base_branch_name, filter)


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


def get_default_branch_remote_ref(folder_path: Path) -> Optional[str]:
    """Return the remote-tracking ref for the default branch, e.g. ``origin/main``.

    The local default branch is often stale behind ``origin/<default>``, and a
    feature branch is typically created from the up-to-date remote ref. Comparing
    against the local branch would therefore fall back to an old merge base and
    surface every commit the default branch has made since as if they were this
    branch's changes. Prefer the remote ref that actually represents the baseline
    for the PR, falling back to the local branch only when the remote ref is not
    available locally.
    """
    branch = get_default_branch(folder_path)
    if not branch:
        return None
    # Refresh the remote-tracking ref first. The local ref can lag behind the
    # remote (e.g. the user has not run fetch/pull since the default branch
    # moved), and a stale ref would drag the merge base back and surface
    # unrelated default-branch commits. Failures are ignored: the verify below
    # falls back to the local branch when the remote ref is unavailable.
    fetch_default_branch(folder_path, branch)
    remote_ref = f"origin/{branch}"
    result = exec_command(folder_path, ["git", "rev-parse", "--verify", remote_ref])
    if result and result.process.returncode == 0:
        return remote_ref
    return branch


def fetch_default_branch(folder_path: Path, branch: str) -> None:
    """Best-effort refresh of the remote-tracking ref for ``branch``.

    Network or permission failures are intentionally ignored: the caller falls
    back to the local ref when the fetch does not succeed.
    """
    result = exec_command(
        folder_path, ["git", "fetch", "origin", branch]
    )
    if not result or result.process.returncode != 0:
        return


def get_current_branch(folder_path: Path) -> Optional[str]:
    result = exec_command(folder_path, ["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if result and result.process.returncode == 0:
        return result.process.stdout.rstrip()
    return None


def exec_command(folder_path: Path, cmd: List[str]) -> ShellExecutionSummary:
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
