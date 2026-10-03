import pytest
from coercion import coerce_bool

# Settings are user-editable JSON, so the values arriving here are whatever the
# user actually typed. The cases below are ordered from the values we expect to
# the malformed ones we have to survive.


@pytest.mark.parametrize(
    ("value", "expected_result"),
    [
        (True, True),
        (False, False),
    ],
)
def test_booleans_pass_through(value: bool, expected_result: bool) -> None:
    assert coerce_bool(value, True) is expected_result


@pytest.mark.parametrize("value", ["true", "TRUE", "yes", "on", "1", "  true  "])
def test_recognised_strings_are_true(value: str) -> None:
    assert coerce_bool(value, False) is True


@pytest.mark.parametrize("value", ["false", "FALSE", "no", "off", "0", "  false  "])
def test_recognised_strings_are_false(value: str) -> None:
    # a quoted false must not read as true, which is what plain bool() would do
    assert coerce_bool(value, True) is False


@pytest.mark.parametrize("value", ['"false"', "'no'", ' " off " '])
def test_quoted_strings_are_stripped(value: str) -> None:
    # a value double-quoted by mistake is still readable
    assert coerce_bool(value, True) is False


@pytest.mark.parametrize("value", [1, 0, 1.0, 0.0])
def test_numbers_mean_what_they_look_like(value: float) -> None:
    # 0 reads as off, not as an unrecognised value falling back to the default
    assert coerce_bool(value, False) is bool(value)


@pytest.mark.parametrize("default", [True, False])
@pytest.mark.parametrize("value", ["maybe", "", "truthy", None, [], {}])
def test_unrecognised_values_fall_back_to_default(value: object, default: bool) -> None:
    # an unrecognised value must not be guessed at, or a typo in the settings
    # file would silently flip the setting
    assert coerce_bool(value, default) is default
