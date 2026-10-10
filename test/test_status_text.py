import pytest
from pathlib import Path

from codeownerinsights.codeowners import CodeOwnerSpecification
from codeownerinsights.status_text import (
    DEFAULT_STATUS_TEMPLATE,
    format_comment,
    render_status_text,
)


def make_spec(
    nearest_comment=None,
    glob_pattern='src/',
    owners=None,
    line_number=1,
    codeowners_file_path=Path('.github/CODEOWNERS'),
):
    return CodeOwnerSpecification(
        nearest_comment,
        glob_pattern,
        owners if owners is not None else ['keith-hall'],
        line_number,
        codeowners_file_path,
    )


# The status bar is a fixed string today, so the default template has to keep
# producing exactly what the plugin showed before it became configurable. If
# this test needs changing, the status bar has changed for every existing user.


def test_default_template_renders_as_before() -> None:
    spec = make_spec('# Backend team\n', owners=['keith-hall', '@platform'])

    assert (
        render_status_text(DEFAULT_STATUS_TEMPLATE, spec)
        == 'Code Owner: Backend team - keith-hall, @platform'
    )


def test_default_template_without_a_comment() -> None:
    # no trailing dash or doubled space to tidy up: the value renders empty and
    # the surrounding whitespace is collapsed
    spec = make_spec(nearest_comment=None, owners=['keith-hall'])

    assert render_status_text(DEFAULT_STATUS_TEMPLATE, spec) == 'Code Owner: - keith-hall'


@pytest.mark.parametrize(
    ('template', 'expected_result'),
    [
        ('{owners}', 'keith-hall, @platform'),
        ('{owner}', 'keith-hall'),
        ('{comment}', 'Backend team'),
        ('{pattern}', 'src/api/'),
        ('{line_number}', '42'),
        ('{codeowners_file}', '.github/CODEOWNERS'),
        ('@{owner}', '@keith-hall'),
        ('{pattern} -> {owners}', 'src/api/ -> keith-hall, @platform'),
        ('no placeholders here', 'no placeholders here'),
        ('', ''),
        ('   ', ''),
    ],
)
def test_known_keys_are_substituted(template: str, expected_result: str) -> None:
    spec = make_spec(
        '# Backend team\n',
        glob_pattern='src/api/',
        owners=['keith-hall', '@platform'],
        line_number=42,
    )

    assert render_status_text(template, spec) == expected_result


def test_the_same_key_can_be_used_more_than_once() -> None:
    spec = make_spec(owners=['keith-hall'])

    assert render_status_text('{owner} {owner}', spec) == 'keith-hall keith-hall'


def test_an_unknown_key_is_left_alone() -> None:
    # an unsubstituted key is the only clue the user gets that it is misspelled,
    # and raising here would put an exception in the editor's event loop
    spec = make_spec(owners=['keith-hall'])

    assert render_status_text('{owners} {nonexistent}', spec) == ('keith-hall {nonexistent}')


def test_a_value_containing_braces_is_not_reinterpreted() -> None:
    # a backslash or brace inside a comment must be inserted verbatim, not
    # treated as part of the template
    spec = make_spec('# see \\d{2} below', owners=['keith-hall'])

    assert render_status_text('{comment}', spec) == r'see \d{2} below'


def test_an_empty_owner_list_renders_as_nothing() -> None:
    # a CODEOWNERS line may name no owner at all, and the plugin only calls this
    # when there is at least one, but the template must not break if it does
    spec = make_spec(owners=[])

    assert render_status_text('owner: {owner}', spec) == 'owner:'


@pytest.mark.parametrize(
    ('comment', 'expected_result'),
    [
        (None, ''),
        ('', ''),
        ('# Backend team', 'Backend team'),
        ('# Backend team\n# second line', 'Backend team second line'),
        ('#Backend team', 'Backend team'),
        ('#   padded   ', 'padded'),
        ('# \n# Backend team\n#', 'Backend team'),
        ('# leading and trailing', 'leading and trailing'),
    ],
)
def test_comments_flatten_onto_one_line(comment, expected_result: str) -> None:
    assert format_comment(comment) == expected_result
