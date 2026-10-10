"""Rendering of the status bar text for a resolved code owner.

The text is a user-configurable template with ``{key}`` placeholders, so the
substitution lives here rather than in the plugin: a malformed template is
something worth asserting on, and this module has to stay free of Sublime Text
imports to be importable at all.
"""

import re
from typing import Dict, Optional

from .codeowners import CodeOwnerSpecification

DEFAULT_STATUS_TEMPLATE = 'Code Owner: {comment? - }{owners}'

# A placeholder is either ``{key}``, substituted with the key's value, or
# ``{key?text}``, where the literal text is included only when the key has a
# value. The second form is what lets a separator sit beside a comment and be
# dropped when there is none, instead of leaving a stray dash behind.
_PLACEHOLDER = re.compile(r'\{(\w+)(\?[^}]*)?\}')


def format_comment(comment: Optional[str], separator: str = ' ') -> str:
    """Flatten a comment block onto one line, dropping the leading ``#``s.

    ``separator`` joins the lines: a space suits a status bar, where the result
    has to stay on one line, while the rules quick panel has a second row per
    entry to be a little more readable.
    """
    if not comment:
        return ''

    lines = []
    for line in comment.split('\n'):
        line = line.strip()
        if line.startswith('#'):
            line = line[1:]
        line = line.strip()
        if line:
            lines.append(line)
    return separator.join(lines)


def get_template_replacements(
    specification: CodeOwnerSpecification,
) -> Dict[str, str]:
    """The values a template may refer to, all as strings.

    ``owner`` is the first owner rather than all of them because the status bar
    is width constrained and the first entry is the one usually meant.
    """
    owners = list(specification.owners)
    return {
        'owners': ', '.join(owners),
        'owner': owners[0] if owners else '',
        'comment': format_comment(specification.nearest_comment),
        'pattern': specification.glob_pattern,
        'line_number': str(specification.line_number),
        'codeowners_file': str(specification.codeowners_file_path),
    }


def render_status_text(template: str, specification: CodeOwnerSpecification) -> str:
    """Fill in a status bar template for a resolved code owner.

    A recognised key with nothing to say -- ``{comment}`` for a rule that has no
    comment above it -- renders as nothing, so one template can serve every rule
    rather than needing a special case per rule. A key that is not recognised is
    left exactly as written, because an unsubstituted ``{key}`` is the only clue
    the user gets that their spelling is wrong; nothing here raises on a bad
    template, since a status bar is not worth an exception in the editor.

    Whitespace runs are collapsed afterwards, so a value that came out empty
    cannot leave the gap it was sitting in.
    """
    replacements = get_template_replacements(specification)
    text = _PLACEHOLDER.sub(
        # a function replacement, so a value containing backslashes is not
        # mistaken for a group reference
        lambda match: _render_placeholder(match, replacements),
        template,
    )
    return ' '.join(text.split())


def _render_placeholder(match: re.Match, replacements: Dict[str, str]) -> str:
    key = match.group(1)
    conditional = match.group(2)
    if conditional is None:
        # a plain {key}: substitute the value, or leave it alone when the key
        # is not recognised, since an unsubstituted key is the only clue the
        # user gets that their spelling is wrong
        return replacements.get(key, match.group(0))
    # a {key?text} conditional: the value is followed by the literal text when
    # the key has a value, and the whole thing is dropped when it does not. The
    # text sits after the key, so it is a suffix -- that is what lets a
    # separator beside {comment} vanish with the comment instead of leaving a
    # stray dash in the status bar. A key that is not recognised is left
    # exactly as written, so a misspelled conditional is still obvious.
    if key not in replacements:
        return match.group(0)
    value = replacements[key]
    return value + conditional[1:] if value else ''
