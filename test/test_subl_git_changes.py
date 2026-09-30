import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codeowners import CodeOwnerSpecification, parse_code_owners
from subl_git_changes import (
    get_git_change_owners,
    get_git_change_owners_for_folder,
    get_code_owner,
    get_code_owner_specifications_for_folder,
    get_project_folders,
    get_project_folders_for_file,
)


def git(cwd: Path, *args: str) -> str:
    import subprocess

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


class MockWindow:
    def __init__(self, folders: List[str]):
        self._folders = folders

    def folders(self) -> Iterable[str]:
        return self._folders


class MockCodeOwnerSpec:
    def __init__(self, owners: List[str], pattern: str):
        self.owners = owners
        self.pattern = pattern


def git(cwd: Path, *args: str) -> str:
    import subprocess

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
def temp_repo(tmp_path: Path) -> Path:
    """A repo on a feature branch with a local 'origin' remote and 2 commits to compare."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(tmp_path, "init", "--bare", "--initial-branch=main", str(origin))

    folder = tmp_path / "repo"
    folder.mkdir()
    git(folder, "init", "--initial-branch=main")
    git(folder, "config", "user.name", "Test")
    git(folder, "config", "user.email", "test@test.com")
    git(folder, "config", "commit.gpgsign", "false")

    codeowners_content = """*.py @python-team
docs/* @docs-team
"""
    write_file(folder, "CODEOWNERS", codeowners_content)
    write_file(folder, "main.py", "print('hello')\n")
    write_file(folder, "docs/readme.md", "# Readme\n")
    commit_all(folder, "initial commit")
    git(folder, "remote", "add", "origin", str(origin))
    git(folder, "push", "--set-upstream", "origin", "main")
    git(folder, "remote", "set-head", "origin", "main")

    git(folder, "checkout", "-b", "feature")
    write_file(folder, "new.py", "print('new')\n")
    commit_all(folder, "feature changes")

    return folder


def test_get_project_folders():
    window = MockWindow(["/project1", "/project2"])
    folders = list(get_project_folders(window))
    assert folders == ["/project1", "/project2"]


def test_get_project_folders_for_file():
    window = MockWindow(["/project/src", "/other"])
    file_path = Path("/project/src/main.py")
    folders = list(get_project_folders_for_file(file_path, window))
    assert folders == [Path("/project/src")]

    file_path2 = Path("/other/file.txt")
    folders2 = list(get_project_folders_for_file(file_path2, window))
    assert folders2 == [Path("/other")]

    file_path3 = Path("/unrelated/file.txt")
    folders3 = list(get_project_folders_for_file(file_path3, window))
    assert folders3 == []


def test_get_code_owner_specifications_for_folder(temp_repo: Path):
    cache = {}

    def get_cached(window, folder):
        return cache.get(folder)

    def set_cached(window, folder, entry):
        cache[folder] = entry

    window = MockWindow([str(temp_repo)])
    specs = get_code_owner_specifications_for_folder(
        window, temp_repo, get_cached, set_cached
    )
    specs = list(specs) if specs else []

    assert len(specs) == 2
    assert any(s.owners == ["@python-team"] for s in specs)
    assert any(s.owners == ["@docs-team"] for s in specs)

    # Second call should use cache
    specs2 = get_code_owner_specifications_for_folder(
        window, temp_repo, get_cached, set_cached
    )
    specs2 = list(specs2) if specs2 else []
    assert specs2 == specs


def test_get_code_owner_specifications_for_folder_cache_invalid(temp_repo: Path):
    cache = {}

    def get_cached(window, folder):
        return cache.get(folder)

    def set_cached(window, folder, entry):
        cache[folder] = entry

    window = MockWindow([str(temp_repo)])

    # First call populates cache
    specs1 = get_code_owner_specifications_for_folder(
        window, temp_repo, get_cached, set_cached
    )
    specs1 = list(specs1) if specs1 else []

    # Modify CODEOWNERS file
    codeowners_file = temp_repo / "CODEOWNERS"
    codeowners_file.write_text("*.js @js-team\n")

    # Should re-parse because mtime changed
    specs2 = get_code_owner_specifications_for_folder(
        window, temp_repo, get_cached, set_cached
    )
    specs2 = list(specs2) if specs2 else []
    assert any(s.owners == ["@js-team"] for s in specs2)


def test_get_code_owner(temp_repo: Path):
    cache = {}

    def get_cached(window, folder):
        return cache.get(folder)

    def set_cached(window, folder, entry):
        cache[folder] = entry

    window = MockWindow([str(temp_repo)])

    # Test Python file
    owner = get_code_owner(
        window, temp_repo, temp_repo / "main.py", get_cached, set_cached
    )
    assert owner is not None
    assert owner.owners == ["@python-team"]

    # Test docs file
    owner = get_code_owner(
        window, temp_repo, temp_repo / "docs" / "readme.md", get_cached, set_cached
    )
    assert owner is not None
    assert owner.owners == ["@docs-team"]

    # Test unowned file
    owner = get_code_owner(
        window, temp_repo, temp_repo / "unowned.txt", get_cached, set_cached
    )
    assert owner is None


def test_get_git_change_owners_for_folder(temp_repo: Path):
    cache = {}

    def get_cached(window, folder):
        return cache.get(folder)

    def set_cached(window, folder, entry):
        cache[folder] = entry

    window = MockWindow([str(temp_repo)])

    results = list(
        get_git_change_owners_for_folder(
            window,
            temp_repo,
            include_unowned=False,
            get_cached_specs=get_cached,
            set_cached_specs=set_cached,
        )
    )

    # Should find new.py (added on feature branch)
    assert len(results) == 1
    folder, file, owner = results[0]
    assert folder == temp_repo
    assert file == Path("new.py")
    assert owner is not None
    assert owner.owners == ["@python-team"]


def test_get_git_change_owners_for_folder_include_unowned(temp_repo: Path):
    cache = {}

    def get_cached(window, folder):
        return cache.get(folder)

    def set_cached(window, folder, entry):
        cache[folder] = entry

    window = MockWindow([str(temp_repo)])

    # Add an unowned file
    (temp_repo / "unowned.txt").write_text("unowned\n")
    os.system(f"git -C {temp_repo} add unowned.txt")
    os.system(f"git -C {temp_repo} commit -m 'add unowned' -q")

    results = list(
        get_git_change_owners_for_folder(
            window,
            temp_repo,
            include_unowned=True,
            get_cached_specs=get_cached,
            set_cached_specs=set_cached,
        )
    )

    assert len(results) == 2
    owners = [r[2].owners if r[2] else [] for r in results]
    assert ["@python-team"] in owners
    assert [] in owners


def test_get_git_change_owners_multiple_folders(tmp_path: Path):
    # Create two separate bare origins
    origin1 = tmp_path / "origin1.git"
    origin1.mkdir()
    git(tmp_path, "init", "--bare", "--initial-branch=main", str(origin1))

    origin2 = tmp_path / "origin2.git"
    origin2.mkdir()
    git(tmp_path, "init", "--bare", "--initial-branch=main", str(origin2))

    repo1 = tmp_path / "repo1"
    repo1.mkdir()
    git(repo1, "init", "--initial-branch=main")
    git(repo1, "config", "user.name", "Test")
    git(repo1, "config", "user.email", "test@test.com")
    git(repo1, "config", "commit.gpgsign", "false")
    write_file(repo1, "CODEOWNERS", "*.py @team1\n")
    write_file(repo1, "a.py", "a\n")
    commit_all(repo1, "init")
    git(repo1, "remote", "add", "origin", str(origin1))
    git(repo1, "push", "--set-upstream", "origin", "main")
    git(repo1, "remote", "set-head", "origin", "main")
    git(repo1, "checkout", "-b", "feature")
    write_file(repo1, "b.py", "b\n")
    commit_all(repo1, "feat")

    repo2 = tmp_path / "repo2"
    repo2.mkdir()
    git(repo2, "init", "--initial-branch=main")
    git(repo2, "config", "user.name", "Test")
    git(repo2, "config", "user.email", "test@test.com")
    git(repo2, "config", "commit.gpgsign", "false")
    write_file(repo2, "CODEOWNERS", "*.js @team2\n")
    write_file(repo2, "x.js", "x\n")
    commit_all(repo2, "init")
    git(repo2, "remote", "add", "origin", str(origin2))
    git(repo2, "push", "--set-upstream", "origin", "main")
    git(repo2, "remote", "set-head", "origin", "main")
    git(repo2, "checkout", "-b", "feature")
    write_file(repo2, "y.js", "y\n")
    commit_all(repo2, "feat")

    cache = {}

    def get_cached(window, folder):
        return cache.get(folder)

    def set_cached(window, folder, entry):
        cache[folder] = entry

    window = MockWindow([str(repo1), str(repo2)])

    results = list(
        get_git_change_owners(
            window,
            include_unowned=False,
            get_cached_specs=get_cached,
            set_cached_specs=set_cached,
        )
    )

    assert len(results) == 2
    folders = [r[0] for r in results]
    assert repo1 in folders
    assert repo2 in folders
