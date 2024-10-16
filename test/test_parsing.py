from textwrap import dedent
import pytest
from pathlib import Path
from typing import Optional
from codeowners import parse_code_owners, get_resolved_code_owners_for_file, CodeOwnerSpecification

fake_path = Path('test/CODEOWNERS')

codeowners_content = dedent("""\
    # This is a comment.
    # Each line is a file pattern followed by one or more owners.

    # These owners will be the default owners for everything in
    # the repo. Unless a later match takes precedence,
    # @global-owner1 and @global-owner2 will be requested for
    # review when someone opens a pull request.
    *       @global-owner1 @global-owner2

    # Order is important; the last matching pattern takes the most
    # precedence. When someone opens a pull request that only
    # modifies JS files, only @js-owner and not the global
    # owner(s) will be requested for a review.
    *.js    @js-owner #This is an inline comment.

    # You can also use email addresses if you prefer. They'll be
    # used to look up users just like we do for commit author
    # emails.
    *.go docs@example.com

    # Teams can be specified as code owners as well. Teams should
    # be identified in the format @org/team-name. Teams must have
    # explicit write access to the repository. In this example,
    # the octocats team in the octo-org organization owns all .txt files.
    *.txt @octo-org/octocats

    # In this example, @doctocat owns any files in the build/logs
    # directory at the root of the repository and any of its
    # subdirectories.
    /build/logs/ @doctocat

    # The `docs/*` pattern will match files like
    # `docs/getting-started.md` but not further nested files like
    # `docs/build-app/troubleshooting.md`.
    docs/*  docs@example.com

    # In this example, @octocat owns any file in an apps directory
    # anywhere in your repository.
    apps/ @octocat

    # In this example, @doctocat owns any file in the `/docs`
    # directory in the root of your repository and any of its
    # subdirectories.
    /docs/ @doctocat

    # In this example, any change inside the `/scripts` directory
    # will require approval from @doctocat or @octocat.
    /scripts/ @doctocat @octocat

    # In this example, @octocat owns any file in a `/logs` directory such as
    # `/build/logs`, `/scripts/logs`, and `/deeply/nested/logs`. Any changes
    # in a `/logs` directory will require approval from @octocat.
    **/logs @octocat

    # In this example, @octocat owns any file in the `/apps`
    # directory in the root of your repository except for the `/apps/github`
    # subdirectory, as its owners are left empty. Without an owner, changes
    # to `apps/github` can be made with the approval of any user who has
    # write access to the repository.
    /apps/ @octocat
    /apps/github

    # In this example, @octocat owns any file in the `/apps`
    # directory in the root of your repository except for the `/apps/github2`
    # subdirectory, as this subdirectory has its own owner @doctocat
    #/apps/ @octocat
    /apps/github2 @doctocat

    # test
    z @z
    # another test with no blank lines between these
    # comments and the prev rule
    x @y
""")
codeowners = list(parse_code_owners(fake_path, codeowners_content))


@pytest.mark.parametrize(
    ('path', 'expected_owner'),
    [
        (
            '/build/logs/bar.log',
            CodeOwnerSpecification(
                '# In this example, @octocat owns any file in a `/logs` directory such as\n' +
                '# `/build/logs`, `/scripts/logs`, and `/deeply/nested/logs`. Any changes\n' +
                '# in a `/logs` directory will require approval from @octocat.',
                '**/logs',
                ['@octocat'],
                53,
                fake_path,
            ),
        ),
        (
            '/build/logs/nested/bar.log',
            CodeOwnerSpecification(
                '# In this example, @doctocat owns any files in the build/logs\n' +
                '# directory at the root of the repository and any of its\n' +
                '# subdirectories.',
                '/build/logs/',
                ['@doctocat'],
                30,
                fake_path,
            ),
        ),
        (
            '/apps/github/some.file',
            CodeOwnerSpecification(
                '# In this example, @octocat owns any file in the `/apps`\n' +
                '# directory in the root of your repository except for the `/apps/github`\n' +
                '# subdirectory, as its owners are left empty. Without an owner, changes\n' +
                '# to `apps/github` can be made with the approval of any user who has\n' +
                '# write access to the repository.',
                '/apps/github',
                [],
                61,
                fake_path,
            ),
        ),
        (
            '/some/path/to/file.js',
            CodeOwnerSpecification(
                '# Order is important; the last matching pattern takes the most\n' +
                '# precedence. When someone opens a pull request that only\n' +
                '# modifies JS files, only @js-owner and not the global\n' +
                '# owner(s) will be requested for a review.',
                '*.js',
                ['@js-owner'],
                14,
                fake_path,
            ),
        ),
        (
            '/some/path/to/file.test',
            CodeOwnerSpecification(
                '# These owners will be the default owners for everything in\n' +
                '# the repo. Unless a later match takes precedence,\n' +
                '# @global-owner1 and @global-owner2 will be requested for\n' +
                '# review when someone opens a pull request.',
                '*',
                ['@global-owner1', '@global-owner2'],
                8,
                fake_path,
            ),
        ),
        (
            '/docs/a/b',
            CodeOwnerSpecification(
                '# In this example, @doctocat owns any file in the `/docs`\n' +
                '# directory in the root of your repository and any of its\n' +
                '# subdirectories.',
                '/docs/',
                ['@doctocat'],
                44,
                fake_path,
            ),
        ),
        (
            'a/docs/getting-started.md',
            CodeOwnerSpecification(
                '# The `docs/*` pattern will match files like\n' +
                '# `docs/getting-started.md` but not further nested files like\n' +
                '# `docs/build-app/troubleshooting.md`.',
                'docs/*',
                ['docs@example.com'],
                35,
                fake_path,
            ),
        ),
        (
            'a/docs/build-app/troubleshooting.md',
            CodeOwnerSpecification(
                '# These owners will be the default owners for everything in\n' +
                '# the repo. Unless a later match takes precedence,\n' +
                '# @global-owner1 and @global-owner2 will be requested for\n' +
                '# review when someone opens a pull request.',
                '*',
                ['@global-owner1', '@global-owner2'],
                8, # NOT line 35
                fake_path,
            ),
        ),
        (
            'z',
            CodeOwnerSpecification(
                '# test',
                'z',
                ['@z'],
                70,
                fake_path,
            ),
        ),
        (
            'x',
            CodeOwnerSpecification(
                '# another test with no blank lines between these\n' +
                '# comments and the prev rule',
                'x',
                ['@y'],
                73,
                fake_path,
            ),
        ),
    ]
)
def test_parsing(path: str, expected_owner: Optional[CodeOwnerSpecification]) -> None:
    owner = get_resolved_code_owners_for_file(codeowners, Path(path))
    assert owner == expected_owner
