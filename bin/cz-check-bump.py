#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

"""
Succeed if the conventional commits after `--compare-ref` require a release.

Works around Commitizen's version handling when bumping from a pre-release:

https://github.com/commitizen-tools/commitizen/issues/688#issue-1628052526
"""

import sys
import argparse
import pathlib
import logging

import decli

from commitizen import exceptions  # type: ignore # pylint: disable=import-error
from commitizen import git  # pylint: disable=import-error
from commitizen import bump  # pylint: disable=import-error
from commitizen import config  # pylint: disable=import-error
from commitizen import commands  # pylint: disable=import-error
from commitizen import cli  # pylint: disable=import-error

logger = logging.getLogger(pathlib.Path(sys.argv[0]).stem)

arg_parser = argparse.ArgumentParser(
    description=__doc__.strip(),
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
arg_parser.add_argument(
    "--compare-ref",
    "-c",
    help="The git ref used as the start of the revision range whose commits to check.",
)


def main(args=None):  # pylint: disable=missing-function-docstring
    logging.basicConfig(level=logging.INFO)
    parsed_args = arg_parser.parse_args(args=args)
    conf = config.read_cfg()
    # Inspecting "private" attributes makes code fragile, but reproducing cz's
    # command-line argument parsing also does. Ideally, the `argparse` library adds a
    # stable public API to introspect command-line arguments, but for now:
    bump_cli_parser = decli.cli(  # pylint: disable=protected-access
        cli.data
    )._subparsers._group_actions[0].choices["bump"]
    # Reproduce `commitizen.commands.bump.Bump.__init__()`:
    arguments = {
        action.dest: action.default
        for action in bump_cli_parser._actions  # pylint: disable=protected-access
        if action.default != argparse.SUPPRESS
    }
    bump_cmd = commands.Bump(config=conf, arguments=arguments)

    compare_ref = parsed_args.compare_ref
    if compare_ref is None:
        # Reproduce last version lookup from `commitizen.commands.bump.Bump.__call__()`:
        current_version = bump_cmd.config.settings["version"]
        tag_format = bump_cmd.bump_settings["tag_format"]
        compare_ref = bump.normalize_tag(
            current_version, tag_format=tag_format
        )

    # Remove the rest of the conditions from `commitizen` except for checking commit
    # messages:
    commits = git.get_commits(compare_ref)
    if commits:
        logger.info(
            "Checking commits for version bump increment:\n%s",
            "\n".join(str(commit) for commit in commits),
        )
    increment = bump_cmd.find_increment(commits)

    if increment is not None:
        # Yes, the conventional commits require a version bump.
        print(increment)
        sys.exit(0)
    exc_value = exceptions.NoCommitsFoundError(
        "[NO_COMMITS_FOUND]\n"
        "No commits found to generate a pre-release.\n"
        "To avoid this error, manually specify the increment type with `--increment`"
    )
    exc_value.output_method(exc_value.message)
    sys.exit(exc_value.exit_code)


main.__doc__ = __doc__


if __name__ == "__main__":
    main()
