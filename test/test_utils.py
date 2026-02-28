import pytest
from pathlib import Path
from codeowners import is_path_relative_to

@pytest.mark.parametrize(
    ('path', 'possible_ancestor_folder', 'expected_result'),
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
            '/path/to/somewhere',
            '/path/to/somewhere',
            True,
        ),
        (
            '/foobar/',
            '/foo',
            False,
        ),
        
    ]
)
def test_ancestor_detection(path: str, possible_ancestor_folder: str, expected_result: bool) -> None:
    assert is_path_relative_to(Path(path), Path(possible_ancestor_folder)) == expected_result
