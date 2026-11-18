# Changelog

All notable changes to CodeOwnerInsights are documented here.
The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [Unreleased]

### Added
### Changed
### Fixed

## [0.5.0]

### Added

**`--with-uncommitted` CLI flag.** Adds uncommitted changes, untracked files
included, to the branch changes, for the files a pull request would change once
everything is committed.

**`--root-relative` and `-z` CLI flags.** Take paths as relative to the repository
root, and read NUL-separated paths from stdin, so git's `--name-only -z` output pipes
in from any directory.

**`--owner` and `--not-owner` CLI flags.** Keep or leave out the files an owner
covers, in text and JSON output alike. Case is ignored, and the `@` and the org are
optional.

**`--codeowners-ref` and `--worktree-codeowners` CLI flags.** Read `CODEOWNERS`
at another ref, or from the working tree for the branch changes, to preview edits
to it.

**`read_file_at_ref()`** git helper and **`CODEOWNERS_LOCATIONS`**, the paths GitHub
searches for a `CODEOWNERS` file, in order.

**`head` parameter** on `get_git_changed_files_compared_to_branch()`. Pass `'HEAD'`
to compare committed changes only; the default still compares the merge base with
the working tree.

**`get_git_untracked_files()`** git helper.

### Changed

**The CLI's branch changes are commits only.** It compared the merge base with the
working tree, so uncommitted edits to tracked files were listed as branch changes
while untracked files were not. It now compares with `HEAD`, which is what a pull
request contains. `--with-uncommitted` gives the working-tree view, untracked files
included. The Sublime Text plugin's diff is unchanged.

**The plugin's diff command shows what the pull request will request.** It lists
the files the branch's commits change, and resolves their owners with the base
branch's `CODEOWNERS`, as GitHub does. It used to include uncommitted edits to
tracked files, and used the working tree's `CODEOWNERS`. The popup now names the
ref it read `CODEOWNERS` at. The status bar and the rule commands still follow the
working tree's `CODEOWNERS`, so edits to it show straight away.

**`pull_request` module** with `get_pull_request_changed_files()` and
`get_code_owner_specifications_at_ref()`, shared by the CLI and the plugin.

### Fixed

**The CLI reads the base branch's `CODEOWNERS` for the branch changes**, because
GitHub requests reviewers from that version. JSON output gains `codeowners_ref`,
and text output names the ref. Other modes still read the working tree's copy.

**The CLI fails when it cannot find the default branch** from `origin/HEAD`, with
exit code 1 and a pointer to `--base`, instead of reporting no files.

## [0.4.0]

### Added

**`--with-uncommitted` CLI flag.** Adds uncommitted changes, untracked files
included, to the branch changes, for the files a pull request would change once
everything is committed.

**`head` parameter** on `get_git_changed_files_compared_to_branch()`. Pass `'HEAD'`
to compare committed changes only; the default still compares the merge base with
the working tree.

**`get_git_untracked_files()`** git helper.

**`--staged` and `--unstaged` CLI flags.** Resolve the owners of the index changes
or the working-tree changes (untracked files included), or of both together,
instead of the branch changes. Text output says `No files to resolve` on stderr when
there are none.

**`get_git_staged_files()` and `get_git_unstaged_files()`** git helpers.

**`--group-by owner` CLI flag.** Lists the files under each set of owners that
applies to them, instead of one file per line. Text output only.

**Coloured CLI output.** Owners, rules and unowned files stand out on a terminal.
`--color auto|always|never` controls it; `auto` honours `NO_COLOR` and leaves piped
output plain. JSON is never coloured.

### Changed
### Fixed

## [0.3.1]

### Added

**`codeownerinsights` CLI command.** Prints the owner and deciding rule for each file,
then the owners a set of files needs. With no arguments it uses the current branch's
changes against the default branch, including deleted files, because GitHub requests
code owners for those too. Takes paths or stdin instead, and supports `--base`,
`--no-fetch`, `--all-rules` and `--json`. Also runs as `python -m codeownerinsights`.

**`diff_filter` parameter** on the changed-files git helpers. Defaults to `ACMR`, as
before; pass `ACMRD` to include deletions.

### Changed
### Fixed

## [0.2.1]

### Added

**Default-branch diff compares against the real remote baseline.** The plugin now
fetches `origin/<default>` before computing the merge base, so a stale local default
branch no longer surfaces unrelated commits as this branch's changes. Fetch failures
are ignored and fall back to the local ref.

**Diff runs off the UI thread.** The fetch + diff + owner resolution no longer blocks
Sublime's event loop; a status message shows while it runs.

**`fetch_remote_default_branch` setting.** Opt out of the ~3.5s remote fetch for the
default-branch diff and use the local `origin/<default>` ref as-is. Fast, but stale
refs drag the merge base back and surface unrelated default-branch commits.

**Refresh from remote** link in the diff popup. Re-runs the diff forcing a fetch from
the remote, regardless of the user setting — useful when results look stale while
`fetch_remote_default_branch` is off for speed.

**Status bar text is now configurable** via a `status_bar_template` setting. Keys:
`{owners}`, `{owner}`, `{comment}`, `{pattern}`, `{line_number}`, `{codeowners_file}`.
A recognized key with nothing to say renders as nothing and surrounding whitespace
collapses, so one template serves every rule instead of needing a special case for
uncommented ones. A misspelled key is left in place rather than blanked — the only
clue the user gets. An empty template turns the status bar off.

**`{key?text}` conditional placeholder.** Emits the value plus the text when the key
has a value and nothing when it does not. The default template is now
`Code Owner: {comment? - }{owners}`, so the dash vanishes with the comment instead of
lingering when a rule has no comment.

**Show All Matching Code Owner Rules** command (Ctrl+Shift+O). Lists every CODEOWNERS
rule that matches a file, with the resolved owner pre-selected. Preview opens the
matching line; confirming leaves the editor on it; Esc cancels preview navigation.

**Preview uses transient views.** Opening a preview via `open_file` with
`transient=True` gives a tab-less view that closes automatically when focus leaves, so
the user's own CODEOWNERS file can never become an untitled tab. When CODEOWNERS already
has focus, the preview moves the selection in place instead of replacing the active
view.

**Settings discoverability.** `CodeOwnerInsights.sublime-settings` is now reachable under
Preferences → Package Settings. The menu item uses `edit_settings` with `base_file`, so
users edit their User settings alongside the shipped defaults.

**Library published to PyPI as `codeownerinsights`.** Core parsing, git, and coercion
logic is now importable and reusable outside the Sublime plugin. The git helpers accept
an optional `git=` parameter so a git wrapper can be substituted by replacing the leading
command token.

**Boolean settings and command arguments are narrowed through `coerce_bool`.** A typo
(or a string `"false"` bound as a command argument) can no longer silently flip a
setting; anything unrecognised falls back to the default.

### Changed

**Large CODEOWNERS files no longer slow matching down.** Each rule's pattern is now
compiled once and reused. Previously wcmatch's 256-entry pattern cache thrashed once a
file produced more patterns than that, and every rule was re-parsed for every file —
around 30× slower per rule on a 400-rule file. A rule is also skipped without running
its regex when the path lacks the rule's longest wildcard-free run, which makes
non-matching unanchored rules such as `*.js` or `Dockerfile` about 20× cheaper to check.

**CODEOWNERS glob semantics now follow GitHub's docs, not `git check-ignore`:**

- A leading `/` anchors a pattern to the repository root (`/docs/` matches
  `docs/readme.md`, not `src/docs/readme.md`).
- An unslashed directory pattern matches the directory wherever it sits in the tree
  (`apps/` matches `src/apps/foo.js`).
- Brackets (`[ ]`) match literally; character ranges are not supported, per GitHub's
  CODEOWNERS docs.

The two places `git check-ignore` and CODEOWNERS diverge are now documented:
check-ignore additionally supports `!` to negate a pattern, `\` to escape a leading `#`,
and `[ ]` character classes — all unsupported in GitHub's CODEOWNERS.

**Dropped Python 3.8–3.10 support.** The library targets 3.11+, the plugin 3.14
(Sublime Text 4205+).

**Single-quote formatting** enforced via ruff in CI, with `quote-style = single` and
`line-length = 100`.

**Preview bookkeeping simplified.** The rules quick panel no longer tracks the original
view or already-open state; `sheet.is_transient()` answers whether the preview is still a
sheet we created. Selecting a line by hand is likewise redundant — the `:line` suffix on
the `open_file` argument already positions the caret after the file loads.

**File-based palette entries stay available with no file open.** When the project has a
single folder and no file is open, that folder is treated as the effective file for owner
resolution, keeping the reveal/show commands in the palette. Multi-folder projects are
unchanged.

### Fixed

**Two pattern-matching bugs** caused real files to be misattributed to owners. A leading
slash was not being stripped before matching (so `/docs/` matched nothing), and an
unslashed directory pattern only matched at the root. Both are covered by new test cases
verified against real `git check-ignore` output.

**Anchoring and nesting now match GitHub.** A pattern with a slash in the middle, such
as `docs/*` or `src/app.py`, matched at any depth; it now matches only from the
repository root. A pattern without a trailing slash, such as `/build/logs` or `**/logs`,
matched only one level into a directory of that name; it now covers the whole subtree.
Wildcards now match dotfiles, so `*.yml` covers `.github/workflows/ci.yml`.

**Tab-separated rules and indented comments.** A tab between the pattern and its owners
made the whole line the pattern, so the rule matched nothing; any whitespace now
separates them. A comment line with leading whitespace is no longer parsed as a rule.
Matching is also case-sensitive with `/` separators on every platform, as on GitHub,
rather than following wcmatch's platform defaults.

**Comment rendering.** A two-line comment no longer renders as
`"Backend teamsecond line"`; comments are joined with `" · "`. The old flattening stripped
`"\n#"` without replacing it with a space.

**Popup link targeting.** With multiple project folders open, every link in the diff
popup previously opened the wrong file. Each file now carries its own folder.

**Stale return annotation** on `get_git_change_owners` (claimed 2-tuples; it yields
3-tuples). Type-checker errors cleared; no runtime change.
