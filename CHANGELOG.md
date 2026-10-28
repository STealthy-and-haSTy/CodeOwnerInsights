# Changelog

All notable changes to CodeOwnerInsights are documented here.
The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [Unreleased]

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