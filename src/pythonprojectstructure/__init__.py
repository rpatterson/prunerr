"""
Python project structure foundation or template, top-level package.
"""

import argparse

# Manage version through the VCS CI/CD process
try:
    from . import version
except ImportError:  # pragma: no cover
    version = None
if version is not None:  # pragma: no cover
    __version__ = version.version

# Define command line options and arguments
parser = argparse.ArgumentParser(
    description=__doc__.strip(),
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)


def main(args=None):
    parser.parse_args(args=args)


main.__doc__ = __doc__
