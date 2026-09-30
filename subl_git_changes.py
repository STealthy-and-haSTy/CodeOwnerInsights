from typing import Iterable, Optional, List, Tuple, Callable, Protocol
from pathlib import Path
import os

from codeowners import (
    CodeOwnerSpecification,
    get_code_owners_file,
    parse_code_owners,
    get_resolved_code_owners_for_file,
    is_path_relative_to,
)
from git import get_git_changed_files_compared_to_default_branch


class WindowLike(Protocol):
    def folders(self) -> Iterable[str]: ...


CacheEntry = Tuple[List[CodeOwnerSpecification], float]
GetCacheFunc = Callable[[object, Path], Optional[CacheEntry]]
SetCacheFunc = Callable[[object, Path, CacheEntry], None]


def get_git_change_owners_for_folder(
    window: WindowLike,
    folder_path: Path,
    include_unowned: bool,
    get_cached_specs: GetCacheFunc,
    set_cached_specs: SetCacheFunc,
) -> Iterable[Tuple[Path, Path, Optional[CodeOwnerSpecification]]]:
    for file_path in get_git_changed_files_compared_to_default_branch(folder_path):
        owner = get_code_owner(
            window,
            folder_path,
            folder_path / file_path,
            get_cached_specs,
            set_cached_specs,
        )
        if owner or include_unowned:
            yield (folder_path, file_path, owner)


def get_git_change_owners(
    window: WindowLike,
    include_unowned: bool,
    get_cached_specs: GetCacheFunc,
    set_cached_specs: SetCacheFunc,
) -> Iterable[Tuple[Path, Path, Optional[CodeOwnerSpecification]]]:
    for folder_path in window.folders():
        for result in get_git_change_owners_for_folder(
            window,
            Path(folder_path),
            include_unowned,
            get_cached_specs,
            set_cached_specs,
        ):
            yield result


def get_code_owner_specifications_for_folder(
    window: object,
    folder_path: Path,
    get_cached_specs: GetCacheFunc,
    set_cached_specs: SetCacheFunc,
) -> Optional[Iterable[CodeOwnerSpecification]]:
    cache_entry = get_cached_specs(window, folder_path)
    if cache_entry:
        codeowners_file = get_code_owners_file(folder_path)
        if codeowners_file and cache_entry[1] == codeowners_file.stat().st_mtime:
            return cache_entry[0]

    codeowners_file = get_code_owners_file(folder_path)
    if codeowners_file:
        modification_time = codeowners_file.stat().st_mtime
        specifications = list(
            parse_code_owners(
                codeowners_file, codeowners_file.read_text(encoding="utf-8")
            )
        )

        set_cached_specs(window, folder_path, (specifications, modification_time))
        return specifications

    return None


def get_code_owner(
    window: object,
    folder_path: Path,
    file_name: Path,
    get_cached_specs: GetCacheFunc,
    set_cached_specs: SetCacheFunc,
) -> Optional[CodeOwnerSpecification]:
    specifications = get_code_owner_specifications_for_folder(
        window, folder_path, get_cached_specs, set_cached_specs
    )

    if specifications:
        relevant_codeowner_specification = get_resolved_code_owners_for_file(
            specifications, Path(os.path.relpath(file_name, folder_path))
        )
        if relevant_codeowner_specification:
            return relevant_codeowner_specification

    return None


def get_project_folders(window: WindowLike) -> Iterable[str]:
    return window.folders()


def get_project_folders_for_file(file_path: Path, window: WindowLike) -> Iterable[Path]:
    for folder in window.folders():
        folder_path = Path(folder)
        if not is_path_relative_to(file_path, folder_path):
            continue
        yield folder_path
