# codeownerinsights

Parse GitHub's [`CODEOWNERS`](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
file and work out who owns a given file: which rules match it, and which one
wins. Pure Python, no editor dependency.

```sh
pip install codeownerinsights
```

Requires Python 3.8 or newer. The only runtime dependency is
[`wcmatch`](https://pypi.org/project/wcmatch/), for GitHub-compatible glob
matching.

## Usage

```python
from pathlib import Path

from codeownerinsights import (
    parse_code_owners,
    get_matching_code_owner_specifications_for_file,
    get_resolved_code_owners_for_file,
)

codeowners_path = Path('.github/CODEOWNERS')
codeowners = list(parse_code_owners(codeowners_path, codeowners_path.read_text(encoding='utf-8')))

# every rule that matches, in file order
for spec in get_matching_code_owner_specifications_for_file(codeowners, Path('src/main.py')):
    print(spec.glob_pattern, '->', spec.owners)

# the resolved owner: the last matching rule wins
owner = get_resolved_code_owners_for_file(codeowners, Path('src/main.py'))
print(owner.owners)
```

## What it gives you

**All matching rules, not just the winner.** Most parsers stop at the resolved
owner. `get_matching_code_owner_specifications_for_file` yields every rule that
hits a path, in file order, so you can show a user which earlier rule is being
overridden by a later one — or why an intended rule did not match at all.

**Nearest comment carried with each rule.** Every parsed
`CodeOwnerSpecification` remembers the comment block immediately above it, so a
rule can be presented with its documentation rather than as a bare pattern.

```python
spec.nearest_comment  # '# Frontend rules\n# owned by the web team'
spec.glob_pattern  # '/web/'
spec.owners  # ['@web-team']
spec.line_number  # 5
spec.codeowners_file_path
```

**GitHub's documented semantics, not git's.** Patterns follow GitHub's
`CODEOWNERS` rules literally: a leading `/` anchors the pattern to the repository
root, and a trailing `/` matches the directory and its contents. This is
deliberately *not* the `git check-ignore` convention where a leading slash means
"do not match". The asymmetry that matters in practice is between anchored and
unslashed directory patterns — with a `CODEOWNERS` at the repository root,
`docs/` matches `docs/readme.md` *and* `src/docs/readme.md`, while `/docs/` matches
`docs/readme.md` but not `src/docs/readme.md`.

Where the two differ, we follow GitHub. `git check-ignore` additionally supports
`!` to negate a pattern, `\` to escape a leading `#`, and `[ ]` character classes;
GitHub's `CODEOWNERS` docs list all three as unsupported, and this library does not
handle them. The two do agree on directory and anchoring rules, which is the part
`test/test_matching.py` checks against real `git check-ignore` output.

**Locating the file.** `get_code_owners_file(root)` looks in the three places
GitHub searches, in GitHub's order, and returns the first hit:

```python
get_code_owners_file(Path('.'))
# .github/CODEOWNERS, CODEOWNERS, or docs/CODEOWNERS
```

## Git integration

`codeownerinsights.git` shells out to git to find what changed relative to a
branch, which is what you want to answer "who reviews this PR".

```python
from pathlib import Path
from codeownerinsights.git import get_git_changed_files_compared_to_default_branch

for changed in get_git_changed_files_compared_to_default_branch(Path('.')):
    print(changed)
```

By default this refreshes `origin/<default>` first, so the result reflects the
real remote baseline; pass `fetch_remote=False` to skip the network round trip
and accept a possibly stale baseline. Renamed files are reported under their new
path only, and deletions are dropped.

Every helper accepts an optional `git=` parameter, so a wrapper can be
substituted by replacing the leading command token — useful for injecting
credentials:

```python
get_git_changed_files_compared_to_default_branch(Path('.'), git='my-git-wrapper')
```

No function changes the process working directory; commands run against the
folder passed in via `cwd=`. This matters in hosts like the Sublime Text plugin
host, where all packages share one interpreter.

## Status bar text

`status_text` renders a resolved rule into a status-bar line from a template,
for callers that want configurable wording.

```python
from codeownerinsights.status_text import render_status_text

render_status_text('Code Owner: {comment? - }{owners}', spec)
# 'Code Owner: Frontend rules owned by the web team - @web-team'
```

Available keys are `{owners}`, `{owner}` (the first owner only), `{comment}`,
`{pattern}`, `{line_number}` and `{codeowners_file}`. A key with nothing to say
renders as nothing and the surrounding whitespace is collapsed, so one template
serves every rule. A misspelled key is left in place rather than silently
blanked, and nothing raises on a bad template.

A key can be made conditional: `{key?text}` includes the literal `text` only
when the key has a value, and drops it when it does not. That is how the
example keeps the dash beside `{comment}` when there is a comment and omits it
when there is not, instead of leaving a stray dash behind.

## Used by

This library is the engine behind
[CodeOwnerInsights](https://github.com/STealthy-and-haSTy/CodeOwnerInsights), a
Sublime Text plugin that surfaces the current file's code owner in the status
bar.

## License

MIT.