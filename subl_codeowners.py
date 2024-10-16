import sublime
import sublime_plugin

from typing import Iterable, Optional, Tuple
from pathlib import Path
#from wcmatch.pathlib import Path
import os

from .codeowners import CodeOwnerSpecification, get_code_owners_file, parse_code_owners, get_resolved_code_owners_for_file
from .git import get_git_changed_files_compared_to_default_branch


STATUS_BAR_KEY = 'codeowner'
codeowner_window_cache = {}


def plugin_unloaded() -> None:
    clear_status_bar_for_all_open_windows()


def clear_status_bar_for_all_open_windows():
    for window in sublime.windows():
        for view in window.views():
            view.erase_status(STATUS_BAR_KEY)


class CodeOwnerListener(sublime_plugin.EventListener):
    def on_load_async(self, view: sublime.View): # TODO: EventListener.on_load_async doesn't seem to be called when previewing via Goto Anything if file not already open
        update_code_owner_in_status_bar(view)

    def on_save_async(self, view: sublime.View):
        update_code_owner_in_status_bar(view)

    def on_post_move_async(self, view: sublime.View):
        update_code_owner_in_status_bar(view)

    def on_activated_async(self, view: sublime.View):
        update_code_owner_in_status_bar(view)

    def on_pre_close_window(self, window: sublime.Window):
        if window.id() in codeowner_window_cache:
            del codeowner_window_cache[window.id()]

    def on_load_project_async(self, window: sublime.Window):
        pass # TODO: cache codeowners files


def update_code_owner_in_status_bar(view: sublime.View) -> None:
    codeowner = get_code_owner_for_view(view)
    if not codeowner or not codeowner.owners:
        view.erase_status(STATUS_BAR_KEY)
    else:
        # TODO: have this f-string be configurable in settings
        nearest_comment = codeowner.nearest_comment[1:].replace('\n#', '').strip() if codeowner.nearest_comment else ''
        view.set_status(STATUS_BAR_KEY, f'Code Owner: {nearest_comment} - {", ".join(codeowner.owners)}')


def get_code_owner_for_view(view: sublime.View) -> Optional[CodeOwnerSpecification]:
    file_name = view.file_name()
    if not file_name:
        return None

    window = view.window()
    if not window:
        return None

    for folder_path in get_project_folders_for_file(file_name, window):
        codeowner = get_code_owner(window, folder_path, file_name)
        if codeowner:
            return codeowner

    return None


def get_project_folders_for_file(file_name: Path, window: sublime.Window) -> Iterable[Path]:
    # TODO: this should be relative to git root, which may not be ST project root...
    # `git rev-parse --show-toplevel` returns full path to folder containing .git folder (could be submodule)
    for folder_path in window.folders():
        if not file_name.startswith(folder_path + '/'):
            # file is not under the given folder, so codeowners from the folder don't apply
            # we added a slash in the check above to avoid false positives like a file called `foobar/test` from being matched against a top level folder called `foo`
            continue

        yield Path(folder_path)


def get_code_owner(window: sublime.Window, folder_path: str, file_name: str) -> Optional[CodeOwnerSpecification]:
    # check cache first
    if window.id() not in codeowner_window_cache.keys():
        codeowner_window_cache[window.id()] = dict()
    codeowners = codeowner_window_cache[window.id()].get(folder_path, None)
    if not codeowners:
        codeowners_file = get_code_owners_file(Path(folder_path))
        if codeowners_file:
            codeowners = list(parse_code_owners(codeowners_file, codeowners_file.read_text(encoding='utf-8')))

            codeowner_window_cache[window.id()][folder_path] = codeowners
            def clear_cache() -> None:
                if window.id() in codeowner_window_cache:
                    if folder_path in codeowner_window_cache[window.id()]:
                        del codeowner_window_cache[window.id()][folder_path]
            # TODO: clear cache early when codeowners is saved/reverted or if file time differs from cached i.e. changing branches? or offer entry in command palette for it
            sublime.set_timeout_async(clear_cache, 1000 * 60 * 60) # 60 minutes

    if codeowners:
        relevant_codeowner_specification = get_resolved_code_owners_for_file(codeowners, Path(os.path.relpath(file_name, folder_path)))
        if relevant_codeowner_specification:
            return relevant_codeowner_specification

    return None


def get_git_change_owners_for_folder(window: sublime.Window, folder_path: Path, include_unowned: bool) -> Iterable[Tuple[Path, Optional[CodeOwnerSpecification]]]:
    for file_path in get_git_changed_files_compared_to_default_branch(folder_path):
        owner = get_code_owner(window, folder_path, file_path)
        if owner or include_unowned:
            yield (file_path, owner)


def get_git_change_owners(window: sublime.Window, include_unowned: bool) -> Iterable[Tuple[Path, Optional[CodeOwnerSpecification]]]:
    for folder_path in window.folders():
        for result in get_git_change_owners_for_folder(window, Path(folder_path), include_unowned):
            yield result


class RevealCodeOwnerCommand(sublime_plugin.TextCommand):
    """Open the CODEOWNERS file on the relevant line which applies to the current file."""
    def run(self, edit):
        codeowner = get_code_owner_for_view(self.view)
        if codeowner:
            self.view.window().run_command('open_file', { 'file': str(codeowner.codeowners_file_path) + ':' + str(codeowner.line_number), 'encoded_position': True })

    def is_enabled(self) -> bool:
        codeowner = get_code_owner_for_view(self.view)
        return bool(codeowner)


class ShowCodeOwnersForGitDefaultBranchDiffCommand(sublime_plugin.TextCommand):
    def run(self, edit, include_unowned: bool = False):
        result = list(get_git_change_owners(self.view.window(), include_unowned))
        
        # group by owners
        # TODO: group by owner singular?
        owner_tree = {}
        for file, codeowner_spec in result:
            if codeowner_spec and codeowner_spec.owners:
                owners = ', '.join(codeowner_spec.owners)
            else:
                owners = '*UNOWNED*'
            if owners not in owner_tree:
                owner_tree[owners] = []
            owner_tree[owners].append(str(file))

        # format popup
        popup_content = ''
        for owners in owner_tree.keys():
            popup_content += f'<h2>{owners}</h2>\n<ul>\n' # TODO: html escape
            for file in owner_tree[owners]:
                popup_content += f'<li>{file}</li>\n' # TODO: html escape # TODO: make clickable link to open codeowners file or file changed? hmm # TODO: show comment by file or subgroup by comment then file
            popup_content += '</ul>\n'

        self.view.show_popup(content=popup_content, location=self.view.sel()[0].a)

    def is_enabled(self) -> bool:
        window_id = self.view.window().id()
        if window_id in codeowner_window_cache and codeowner_window_cache[window_id]:
            return True
        return False
