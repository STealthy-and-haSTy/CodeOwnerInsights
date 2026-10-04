"""Rendering of the status bar text for a resolved code owner.

The text is a user-configurable template with ``{key}`` placeholders, so the
substitution lives here rather than in the plugin: a malformed template is
something worth asserting on, and this module has to stay free of Sublime Text
imports to be importable at all.
"""

import re
from typing import Dict, Optional

from .codeowners import CodeOwnerSpecification

DEFAULT_STATUS_TEMPLATE = "Code Owner: {comment} - {owners}"

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def format_comment(comment: Optional[str], separator: str = " ") -> str:
    """Flatten a comment block onto one line, dropping the leading ``#``s.

    ``separator`` joins the lines: a space suits a status bar, where the result
    has to stay on one line, while the rules quick panel has a second row per
    entry to be a little more readable.
    """
    if not comment:
        return ""

    lines = []
    for line in comment.split("\n"):
        line = line.strip()
        if line.startswith("#"):
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
        "owners": ", ".join(owners),
        "owner": owners[0] if owners else "",
        "comment": format_comment(specification.nearest_comment),
        "pattern": specification.glob_pattern,
        "line_number": str(specification.line_number),
        "codeowners_file": str(specification.codeowners_file_path),
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
        lambda match: replacements.get(match.group(1), match.group(0)),
        template,
    )
    return " ".join(text.split())
