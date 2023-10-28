#!/usr/bin/env python

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

"""
Return the current version minus any pre-release suffix along with its type.

Useful to get the final, stable version to bump a earlier pre-release to a final
release.
"""  # pylint: disable=invalid-name

import sys
import argparse

import packaging.version

parser = argparse.ArgumentParser(
    description=__doc__.strip(),
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
parser.add_argument(
    "version",
    metavar='SEMVER',
    help="""The current pre-release version""",
)


def main(args=None):  # pylint: disable=missing-function-docstring
    parsed_args = parser.parse_args(args=args)
    version = packaging.version.parse(parsed_args.version)
    if not version.is_prerelease:
        raise ValueError(f"The current VCS version tag is not a pre-release: {version}")
    version_type = (
        "patch" if version.micro != 0 else
        "minor" if version.minor != 0 else
        "major"
    )
    print(version.base_version, version_type)


main.__doc__ = __doc__


if __name__ == "__main__":
    sys.exit(main())
