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

from .subl_git_changes import (
    get_git_change_owners,
    get_git_change_owners_for_folder,
    get_code_owner,
    get_code_owner_specifications_for_folder,
    get_project_folders,
    get_project_folders_for_file,
)


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

    def as_tuple(self) -> Tuple[List[CodeOwnerSpecification], float]:
        return (self.specifications, self.modification_time)

    @staticmethod
    def from_tuple(
        t: Tuple[List[CodeOwnerSpecification], float],
    ) -> "CodeOwnerCacheEntry":
        return CodeOwnerCacheEntry(t[0], t[1])


def get_code_owner_cache_entry(
    window: sublime.Window, folder_path: Path
) -> Optional[Tuple[List[CodeOwnerSpecification], float]]:
    if window.id() not in codeowner_window_cache.keys():
        codeowner_window_cache[window.id()] = dict()
    entry = codeowner_window_cache[window.id()].get(folder_path, None)
    if entry:
        return entry.as_tuple()
    return None


def set_code_owner_cache_entry(
    window: sublime.Window,
    folder_path: Path,
    entry: Tuple[List[CodeOwnerSpecification], float],
) -> None:
    if window.id() not in codeowner_window_cache.keys():
        codeowner_window_cache[window.id()] = dict()
    codeowner_window_cache[window.id()][folder_path] = CodeOwnerCacheEntry.from_tuple(
        entry
    )


class CodeOwnerListener(sublime_plugin.EventListener):
    def on_load_async(self, view: sublime.View):
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
        pass


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
        codeowner = get_code_owner(
            view.window(),
            folder_path,
            Path(view.file_name()),
            get_code_owner_cache_entry,
            set_code_owner_cache_entry,
        )
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
        result = list(
            get_git_change_owners(
                self.view.window(),
                include_unowned,
                get_code_owner_cache_entry,
                set_code_owner_cache_entry,
            )
        )

        if not result:
            self.view.show_popup(
                content="<p>No changes compared to the default branch.</p>",
                location=self.view.sel()[0].a,
                max_width=300,
                max_height=100,
            )
            return

        owner_tree: dict[str, List[Tuple[str, Path]]] = {}
        for folder, file, codeowner_spec in result:
            if codeowner_spec and codeowner_spec.owners:
                owners = ", ".join(codeowner_spec.owners)
            else:
                owners = "*UNOWNED*"
            if owners not in owner_tree:
                owner_tree[owners] = []
            owner_tree[owners].append((str(file), folder))

        popup_content = ""
        for owners, files in owner_tree.items():
            popup_content += f"<h2>{html.escape(owners)}</h2>\n<ul>\n"

            for file_str, folder in files:
                command_url = sublime.html_format_command(
                    "open_file", {"file": str(folder / file_str)}
                )
                popup_content += (
                    f'<li><a href="{command_url}">{html.escape(file_str)}</a></li>\n'
                )
            popup_content += "</ul>\n"

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
