from textwrap import dedent
import pytest
from pathlib import Path
from typing import Optional
from codeowners import does_codeowner_glob_match

@pytest.mark.parametrize(
    ('path', 'glob', 'expected_result'),
    [
        (
            '/build/logs/foo/bar.log',
            '/build/logs/',
            True,
        ),
        (
            '/build/logs/foo.log',
            '/build/logs/',
            True,
        ),
        (
            '/baz/build/logs/foo/bar.log',
            '/build/logs/',
            False,
        ),
        (
            '/path/to/a/file',
            '*',
            True,
        ),
        (
            '/path/to/a/file.ext',
            '*',
            True,
        ),
        (
            'file.js',
            '*.js',
            True,
        ),
        (
            'path/to/file.js',
            '*.js',
            True,
        ),
        (
            'path/to/file.jsx',
            '*.js',
            False,
        ),
        (
            'docs/getting-started.md',
            'docs/*',
            True,
        ),
        (
            'docs/build-app/troubleshooting.md',
            'docs/*',
            False,
        ),
        (
            '/apps/github/some.file',
            '/apps/github',
            True,
        ),
        (
            '/apps/github/subfolder/some.file',
            '/apps/github',
            False,
        ),
        (
            '/logs/test.log',
            '**/logs',
            True,
        ),
        (
            '/build/logs/test.log',
            '**/logs',
            True,
        ),
        (
            '/logs/subfolder/test.log',
            '**/logs',
            False,
        ),
    ]
)
def test_matching(path: str, glob: str, expected_result: bool) -> None:
    assert does_codeowner_glob_match(glob, path) == expected_result
