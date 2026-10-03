"""Pure helpers for narrowing values that arrive as untyped data.

Settings are user-editable JSON, and command arguments can be supplied by a
keybinding, so neither is guaranteed to be the type the caller wants. These
helpers narrow such values at the boundary rather than asserting a type that
has not actually been checked, which keeps a typo from silently inverting a
setting.

Free of Sublime Text imports, in keeping with codeowners.py and git.py, so the
logic here is testable without a running editor.
"""


def coerce_bool(value: object, default: bool) -> bool:
    """Interpret a value from a settings file or command argument as a boolean.

    Recognises the spellings a user can realistically write. An unrecognised
    value falls back to ``default`` rather than being guessed at, so that a
    malformed entry cannot silently flip the setting.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        # strip quotes as well as space, so a value that was double-quoted by
        # mistake ("\"false\"") is read the same as a bare one
        lowered = value.strip().strip("\"'").strip().lower()
        if lowered in ("true", "yes", "on", "1"):
            return True
        if lowered in ("false", "no", "off", "0"):
            return False
        return default
    if isinstance(value, (int, float)):
        # a numeric boolean means what it looks like, so 0 reads as off rather
        # than as an unrecognised value falling back to the default
        return bool(value)
    return default
