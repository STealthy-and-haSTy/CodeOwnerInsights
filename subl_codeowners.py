import sublime
import sublime_plugin
from typing import Iterable, Optional, List, Tuple
from pathlib import Path
import os
import html
from dataclasses import dataclass

from .codeowners import (
    CodeOwnerSpecification,
    get_code_owners_file,
    parse_code_owners,
    get_resolved_code_owners_for_file,
    is_path_relative_to,
)
from .git import get_git_changed_files_compared_to_default_branch


STATUS_BAR_KEY = "codeowner"
codeowner_window_cache = {}


def plugin_unloaded() -> None:
    clear_status_bar_for_all_open_windows()


def clear_status_bar_for_all_open_windows():
    for window in sublime.windows():
        for view in window.views():
            view.erase_status(STATUS_BAR_KEY)


@dataclass
class CodeOwnerCacheEntry:
    specifications: List[CodeOwnerSpecification]
    modification_time: float

    def is_valid(self, codeowners_file: Path) -> bool:
        return (
            codeowners_file.exists()
            and self.modification_time == codeowners_file.stat().st_mtime
        )


def get_code_owner_cache_entry(
    window: sublime.Window, folder_path: Path
) -> Optional[CodeOwnerCacheEntry]:
    if window.id() not in codeowner_window_cache.keys():
        codeowner_window_cache[window.id()] = dict()
    return codeowner_window_cache[window.id()].get(folder_path, None)


def set_code_owner_cache_entry(
    window: sublime.Window, folder_path: Path, entry: CodeOwnerCacheEntry
) -> None:
    if window.id() not in codeowner_window_cache.keys():
        codeowner_window_cache[window.id()] = dict()
    codeowner_window_cache[window.id()][folder_path] = entry


class CodeOwnerListener(sublime_plugin.EventListener):
    def on_load_async(
        self, view: sublime.View
    ):  # TODO: EventListener.on_load_async doesn't seem to be called when previewing via Goto Anything if file not already open
        update_code_owner_in_status_bar(view)

    def on_post_save_async(self, view: sublime.View):
        clear_cache_when_codeowner_file_saved(view)
        update_code_owner_in_status_bar(view)

    def on_post_move_async(self, view: sublime.View):
        update_code_owner_in_status_bar(view)

    def on_activated_async(self, view: sublime.View):
        update_code_owner_in_status_bar(view)

    def on_pre_close_window(self, window: sublime.Window):
        if window.id() in codeowner_window_cache:
            del codeowner_window_cache[window.id()]

    def on_load_project_async(self, window: sublime.Window):
        pass  # TODO: cache codeowners files


def clear_cache_when_codeowner_file_saved(view: sublime.View) -> None:
    saved_file_path = get_file_path_of_view(view)
    relevant_project_folders = get_project_folders_for_view(view)
    if not relevant_project_folders:
        return

    for project_folder in relevant_project_folders:
        code_owners_path = get_code_owners_file(project_folder)
        if code_owners_path == saved_file_path:
            print(
                f"CodeOwnerInsights: {saved_file_path} has been updated, clearing codeowner cache"
            )
            codeowner_window_cache[view.window().id()] = dict()
            return


def update_code_owner_in_status_bar(view: sublime.View) -> None:
    codeowner = get_code_owner_for_view(view)
    if not codeowner or not codeowner.owners:
        view.erase_status(STATUS_BAR_KEY)
    else:
        # TODO: have this f-string be configurable in settings
        nearest_comment = (
            codeowner.nearest_comment[1:].replace("\n#", "").strip()
            if codeowner.nearest_comment
            else ""
        )
        view.set_status(
            STATUS_BAR_KEY,
            f"Code Owner: {nearest_comment} - {', '.join(codeowner.owners)}",
        )


def get_code_owner_for_view(view: sublime.View) -> Optional[CodeOwnerSpecification]:
    relevant_project_folders = get_project_folders_for_view(view)
    if not relevant_project_folders:
        return None

    for folder_path in relevant_project_folders:
        codeowner = get_code_owner(view.window(), folder_path, view.file_name())
        if codeowner:
            return codeowner

    return None


def get_file_path_of_view(view: sublime.View) -> Optional[Path]:
    file_name = view.file_name()
    if not file_name:
        return None

    return Path(file_name)


def get_project_folders_for_view(view: sublime.View) -> Optional[Iterable[Path]]:
    file_path = get_file_path_of_view(view)

    window = view.window()
    if not window or not file_path:
        return None

    return get_project_folders_for_file(file_path, window)


def get_project_folders_for_file(
    file_path: Path, window: sublime.Window
) -> Iterable[Path]:
    # TODO: this should be relative to git root, which may not be ST project root...
    # `git rev-parse --show-toplevel` returns full path to folder containing .git folder (could be submodule)
    for folder in window.folders():
        folder_path = Path(folder)
        if not is_path_relative_to(file_path, folder_path):
            # file is not under the given folder, so codeowners from the folder don't apply
            continue

        yield folder_path


def get_code_owner(
    window: sublime.Window, folder_path: Path, file_name: Path
) -> Optional[CodeOwnerSpecification]:
    specifications = get_code_owner_specifications_for_folder(window, folder_path)

    if specifications:
        relevant_codeowner_specification = get_resolved_code_owners_for_file(
            specifications, Path(os.path.relpath(file_name, folder_path))
        )
        if relevant_codeowner_specification:
            return relevant_codeowner_specification

    return None


def get_code_owner_specifications_for_folder(
    window: sublime.Window, folder_path: Path
) -> Optional[Iterable[CodeOwnerSpecification]]:
    # check cache first
    cache_entry = get_code_owner_cache_entry(window, folder_path)
    if cache_entry:
        codeowners_file = get_code_owners_file(folder_path)
        if codeowners_file and cache_entry.is_valid(codeowners_file):
            return cache_entry.specifications

    # if not in cache or cache is invalid, parse the file
    codeowners_file = get_code_owners_file(folder_path)
    if codeowners_file:
        modification_time = codeowners_file.stat().st_mtime
        specifications = list(
            parse_code_owners(
                codeowners_file, codeowners_file.read_text(encoding="utf-8")
            )
        )

        set_code_owner_cache_entry(
            window, folder_path, CodeOwnerCacheEntry(specifications, modification_time)
        )
        return specifications

    return None


def get_git_change_owners_for_folder(
    window: sublime.Window, folder_path: Path, include_unowned: bool
) -> Iterable[Tuple[Path, Path, Optional[CodeOwnerSpecification]]]:
    for file_path in get_git_changed_files_compared_to_default_branch(folder_path):
        # git diff --name-only reports paths relative to the folder it was run in
        owner = get_code_owner(window, folder_path, folder_path / file_path)
        if owner or include_unowned:
            yield (folder_path, file_path, owner)


def get_git_change_owners(
    window: sublime.Window, include_unowned: bool
) -> Iterable[Tuple[Path, Optional[CodeOwnerSpecification]]]:
    for folder_path in window.folders():
        for result in get_git_change_owners_for_folder(
            window, Path(folder_path), include_unowned
        ):
            yield result


class RevealCodeOwnerCommand(sublime_plugin.TextCommand):
    """Open the CODEOWNERS file on the relevant line which applies to the current file."""

    def run(self, edit):
        codeowner = get_code_owner_for_view(self.view)
        if codeowner:
            self.view.window().run_command(
                "open_file",
                {
                    "file": str(codeowner.codeowners_file_path)
                    + ":"
                    + str(codeowner.line_number),
                    "encoded_position": True,
                },
            )

    def is_enabled(self) -> bool:
        codeowner = get_code_owner_for_view(self.view)
        return bool(codeowner)


class ShowCodeOwnersForGitDefaultBranchDiffCommand(sublime_plugin.TextCommand):
    def run(self, edit, include_unowned: bool = False):
        # The git work (fetch + diff + owner resolution) can take a couple of
        # seconds and is network-bound, so run it off the UI thread. Without
        # this the command blocks Sublime's event loop and the editor freezes
        # until it finishes. Show a status message first so the wait is visible.
        self.view.set_status(
            STATUS_BAR_KEY, "CodeOwnerInsights: computing git diff..."
        )
        sublime.set_timeout_async(
            lambda: self._compute_and_show(self.view.window(), include_unowned), 0
        )

    def _compute_and_show(
        self, window: sublime.Window, include_unowned: bool
    ) -> None:
        try:
            result = list(get_git_change_owners(window, include_unowned))
        finally:
            # clear the status message on the UI thread once the work is done
            sublime.set_timeout(lambda: self.view.erase_status(STATUS_BAR_KEY), 0)

        owner_tree = self._group_by_owners(result)
        popup_content = self._format_popup(owner_tree)
        sublime.set_timeout(lambda: self._show_popup(popup_content), 0)

    @staticmethod
    def _group_by_owners(
        result: Iterable[Tuple[Path, Path, Optional[CodeOwnerSpecification]]]
    ) -> dict:
        # group by owners, keeping each file together with the folder it lives
        # in so the open-file link resolves to the right project folder
        owner_tree: dict = {}
        for folder, file, codeowner_spec in result:
            if codeowner_spec and codeowner_spec.owners:
                owners = ", ".join(codeowner_spec.owners)
            else:
                owners = "*UNOWNED*"
            owner_tree.setdefault(owners, []).append((folder, file))
        return owner_tree

    @staticmethod
    def _format_popup(owner_tree: dict) -> str:
        popup_content = ""
        for owners in owner_tree.keys():
            popup_content += f"<h2>{html.escape(owners)}</h2>\n<ul>\n"

            for folder, file in owner_tree[owners]:
                command_url = sublime.html_format_command(
                    "open_file", {"file": str(folder / file)}
                )
                popup_content += (
                    f'<li><a href="{command_url}">{html.escape(str(file))}</a></li>\n'
                )
            popup_content += "</ul>\n"
        return popup_content

    def _show_popup(self, popup_content: str) -> None:
        if not popup_content:
            self.view.erase_status(STATUS_BAR_KEY)
            return
        self.view.show_popup(
            content=popup_content,
            location=self.view.sel()[0].a,
            on_navigate=self.navigate,
            max_width=540,
            max_height=320,
        )

    def is_enabled(self) -> bool:
        window_id = self.view.window().id()
        if window_id in codeowner_window_cache and codeowner_window_cache[window_id]:
            return True
        return False

    def navigate(self, link: str) -> None:
        if link.startswith("subl:"):
            link = link[len("subl:") :]

        if open_angle_pos := link.find("{"):
            command_args = sublime.decode_value(link[open_angle_pos:])
            command_name = link[0:open_angle_pos].strip()
        else:
            command_args = dict()
            command_name = link.strip()

        self.view.window().run_command(command_name, command_args)
