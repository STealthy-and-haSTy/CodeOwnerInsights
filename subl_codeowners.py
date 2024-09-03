import sublime
import sublime_plugin

from typing import Optional
from pathlib import Path

from .codeowners import CodeOwnerSpecification, get_code_owners_file, parse_code_owners, get_resolved_code_owners_for_file


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
        del codeowner_window_cache[window.id()]

    def on_load_project_async(self, window: sublime.Window):
        pass # TODO: cache codeowners files


def update_code_owner_in_status_bar(view: sublime.View) -> None:
    codeowner = get_code_owner_for_view(view)
    if not codeowner:
        view.erase_status(STATUS_BAR_KEY)
    else:
        # TODO: have this f-string be configurable in settings
        nearest_comment = codeowner.nearest_comment[1:].strip() if codeowner.nearest_comment else ''
        view.set_status(STATUS_BAR_KEY, f'Code Owner: {nearest_comment} - {", ".join(codeowner.owners)}')


def get_code_owner_for_view(view: sublime.View) -> Optional[CodeOwnerSpecification]:
    # TODO: this should be relative to git root, which may not be ST project root...
    # `git rev-parse --show-toplevel` returns full path to folder containing .git folder (could be submodule)
    file_name = view.file_name()
    if not file_name:
        return None

    window = view.window()
    if not window:
        return None

    for folder_path in window.folders():
        if not file_name.startswith(folder_path + '/'):
            # file is not under the given folder, so codeowners from the folder don't apply
            # we added a slash in the check above to avoid false positives like a file called `foobar/test` from being matched against a top level folder called `foo`
            continue

        # check cache first
        if window.id() not in codeowner_window_cache.keys():
            codeowner_window_cache[window.id()] = dict()
        codeowners = codeowner_window_cache[window.id()].get(folder_path, None)
        if not codeowners:
            codeowners_file = get_code_owners_file(Path(folder_path))
            if codeowners_file:
                codeowners = list(parse_code_owners(codeowners_file.read_text(encoding='utf-8')))

                codeowner_window_cache[window.id()][folder_path] = codeowners
                def clear_cache() -> None:
                    del codeowner_window_cache[window.id()][folder_path]
                # TODO: clear cache early when codeowners is saved/reverted or if file time differs from cached i.e. changing branches? or offer entry in command palette for it
                sublime.set_timeout_async(clear_cache, 1000 * 60 * 60) # 60 minutes

        if codeowners:
            relevant_codeowner_specification = get_resolved_code_owners_for_file(codeowners, Path(file_name))
            if relevant_codeowner_specification:
                return relevant_codeowner_specification

    return None


# TODO: command palette entry to show more information like line, reason comment etc.
#       - maybe even reveal line by opening codeowners in ST and moving selection to relevant line
