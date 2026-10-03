import os
import subprocess
import sys
from pathlib import Path

import pytest

from git import (
    exec_command,
    get_current_branch,
    get_default_branch,
    get_git_changed_files_compared_to_branch,
    get_git_changed_files_compared_to_default_branch,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the non-Windows code path shells out to bash"
)


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def write_file(folder: Path, relative_path: str, content: str) -> Path:
    path = folder / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def commit_all(folder: Path, message: str) -> None:
    git(folder, "add", "-A")
    git(folder, "commit", "-m", message, "--no-gpg-sign")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo on a feature branch with a local 'origin' remote and 2 commits to compare."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(tmp_path, "init", "--bare", "--initial-branch=main", str(origin))

    folder = tmp_path / "repo"
    folder.mkdir()
    git(folder, "init", "--initial-branch=main")
    git(folder, "config", "user.name", "CodeOwnerInsights")
    git(folder, "config", "user.email", "test@example.com")
    git(folder, "config", "commit.gpgsign", "false")

    write_file(folder, "main.py", "# main\n")
    write_file(folder, "src/kept.py", "# kept\n")
    write_file(folder, "src/removed.py", "# removed\n")
    commit_all(folder, "initial commit")
    git(folder, "remote", "add", "origin", str(origin))
    git(folder, "push", "--set-upstream", "origin", "main")
    git(folder, "remote", "set-head", "origin", "main")

    git(folder, "checkout", "-b", "feature")
    write_file(folder, "src/added.py", "# added\n")
    (folder / "src" / "removed.py").unlink()
    git(folder, "mv", "main.py", "src/renamed.py")
    commit_all(folder, "feature changes")

    return folder


def test_get_current_branch(repo: Path) -> None:
    assert get_current_branch(repo) == "feature"


def test_get_default_branch(repo: Path) -> None:
    assert get_default_branch(repo) == "main"


def test_changed_files_compared_to_branch(repo: Path) -> None:
    # the deleted file is excluded by --diff-filter=ACMR, and a rename is
    # reported under its new path only
    files = set(get_git_changed_files_compared_to_branch(repo, "main"))
    assert files == {
        Path("src/added.py"),
        Path("src/renamed.py"),
    }


def test_changed_files_compared_to_branch_with_no_changes(repo: Path) -> None:
    git(repo, "checkout", "main")
    assert list(get_git_changed_files_compared_to_branch(repo, "main")) == []


def test_changed_files_compared_to_branch_with_unknown_branch(repo: Path) -> None:
    assert list(get_git_changed_files_compared_to_branch(repo, "no-such-branch")) == []


def test_changed_files_compared_to_branch_passes_filter_through(repo: Path) -> None:
    files = set(
        get_git_changed_files_compared_to_branch(repo, "main", filter="--relative=src/")
    )
    assert files == {Path("added.py"), Path("renamed.py")}


def test_changed_files_compared_to_default_branch(repo: Path) -> None:
    files = set(get_git_changed_files_compared_to_default_branch(repo))
    assert files == {
        Path("src/added.py"),
        Path("src/renamed.py"),
    }


def test_changed_files_compared_to_default_branch_with_filter(repo: Path) -> None:
    files = set(
        get_git_changed_files_compared_to_default_branch(repo, filter="--relative=src/")
    )
    assert files == {Path("added.py"), Path("renamed.py")}


@pytest.fixture
def repo_with_stale_local_default(tmp_path: Path) -> Path:
    """The default branch on origin is ahead of the local default branch.

    This reproduces the real-world situation where the user's local ``main``/
    ``master`` has not been fast-forwarded to ``origin/main`` yet, and the feature
    branch was created from the up-to-date ``origin/main``. Comparing against the
    stale local default would drag the merge base back and surface every commit
    the default branch has made since as if they were this branch's changes.
    """
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(tmp_path, "init", "--bare", "--initial-branch=main", str(origin))

    folder = tmp_path / "repo"
    folder.mkdir()
    git(folder, "init", "--initial-branch=main")
    git(folder, "config", "user.name", "CodeOwnerInsights")
    git(folder, "config", "user.email", "test@example.com")
    git(folder, "config", "commit.gpgsign", "false")

    # commit shared by the local default, origin, and the feature branch
    write_file(folder, "shared.py", "# shared\n")
    commit_all(folder, "shared commit")
    git(folder, "remote", "add", "origin", str(origin))
    git(folder, "push", "--set-upstream", "origin", "main")
    git(folder, "remote", "set-head", "origin", "main")

    # advance origin/main beyond the local default
    write_file(folder, "upstream.py", "# upstream\n")
    commit_all(folder, "upstream commit")
    git(folder, "push", "origin", "main")

    # leave the local default behind origin/main
    git(folder, "reset", "--hard", "HEAD~1")

    # create the feature branch from the up-to-date origin/main
    git(folder, "checkout", "-b", "feature", "origin/main")
    write_file(folder, "feature.py", "# feature\n")
    commit_all(folder, "feature changes")

    return folder


def test_changed_files_compare_against_remote_default_branch(
    repo_with_stale_local_default: Path,
) -> None:
    # only the feature branch's own changes are reported, not the unrelated
    # commits that origin/main has made since the local default fell behind
    files = set(
        get_git_changed_files_compared_to_default_branch(
            repo_with_stale_local_default
        )
    )
    assert files == {Path("feature.py")}


def test_changed_files_are_relative_to_the_repo_not_the_cwd(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    files = set(get_git_changed_files_compared_to_default_branch(repo))
    assert Path("src/added.py") in files


def test_exec_command_does_not_change_the_process_cwd(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    exec_command(repo, ["git", "rev-parse", "--abbrev-ref", "HEAD"])
    assert Path.cwd() == elsewhere


def test_git_helpers_do_not_change_the_process_cwd(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    get_current_branch(repo)
    get_default_branch(repo)
    list(get_git_changed_files_compared_to_default_branch(repo))
    assert Path.cwd() == elsewhere


def test_get_current_branch_outside_a_repo(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    assert get_current_branch(not_a_repo) is None


def test_get_default_branch_outside_a_repo(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    # the `| cut` pipeline makes the exit code come from cut, not git, so this
    # returns an empty string rather than None. Callers only test for truthiness
    assert not get_default_branch(not_a_repo)


def test_changed_files_outside_a_repo(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    assert list(get_git_changed_files_compared_to_branch(not_a_repo, "main")) == []
    assert list(get_git_changed_files_compared_to_default_branch(not_a_repo)) == []


def test_exec_command_runs_in_the_given_folder(repo: Path) -> None:
    summary = exec_command(repo, ["pwd"])
    assert summary.process.returncode == 0
    assert os.path.realpath(summary.process.stdout.strip()) == os.path.realpath(
        str(repo)
    )
