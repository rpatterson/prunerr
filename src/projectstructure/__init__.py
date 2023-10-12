# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

# PYTHON_ARGCOMPLETE_OK

"""
Project structure foundation or template, top-level package.
"""

import sys
import logging
import argparse
import json
import pdb
import typing

import argcomplete

from . import utils

logger = logging.getLogger(__name__)

# Manage version through the VCS CI/CD process
__version__ = None
try:
    from . import version
except ImportError:  # pragma: no cover
    pass
else:  # pragma: no cover
    __version__ = version.version

# Define command line options and arguments
parser = argparse.ArgumentParser(
    description=__doc__.strip(),
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
parser.add_argument(
    "--log-level",
    default=argparse.SUPPRESS,
    # The `logging` module provides no public access to all defined levels:
    choices=logging._nameToLevel,  # pylint: disable=protected-access
    help="Select logging verbosity. (default: INFO)",
)
# Define command-line subcommands:
subparsers = parser.add_subparsers(
    dest="command",
    required=True,
    help="subcommand",
)


# TEMPLATE: Replace with the subcommands and arguments your project provides.
def foobar(quiet: bool = False) -> typing.Optional[list]:
    """
    Run the foobar subcommand from the command line.

    :param quiet: Whether to return results
    :return: Subcommand results
    """
    if not quiet:
        return ["foo", "bar"]
    return None


parser_foobar = subparsers.add_parser(
    "foobar",
    help=foobar.__doc__.strip(),  # type: ignore
    description=foobar.__doc__.strip(),  # type: ignore
)
# Make the function for the subcommand specified in the command-line argument available
# in the argument parser for delegation:
parser_foobar.set_defaults(command=foobar)
parser_foobar.add_argument(
    "-q",
    "--quiet",
    action="store_true",
    help="Suppress reporting results",
)

# Register shell tab completion
argcomplete.autocomplete(parser)


def config_cli_logging(
    root_level: int = logging.INFO,
    log_level: str = parser.get_default("--log-level"),
    **_,
):
    """
    Configure logging command-line usage as soon as possible to affect all output.

    :param root_level: Logging level for other packages
    :param log_level: Logging level for this package
    :param _: Ignores other kwargs
    """
    # Set just this package's logger level, not others', from options and environment
    # variables:
    logging.basicConfig(level=root_level)
    # If the command-line option wasn't specified, fallback to the environment variable:
    if log_level is None:
        log_level = "INFO"
        if utils.DEBUG:  # pragma: no cover
            log_level = "DEBUG"
    logger.setLevel(getattr(logging, log_level.strip().upper()))


def main(args=None):  # pylint: disable=missing-function-docstring
    try:
        _main(args=args)
    except Exception:  # pragma: no cover
        if utils.POST_MORTEM:
            pdb.post_mortem()
        raise


def _main(args=None):
    """
    Inner main command-line handler for outer exception handling.
    """
    # Parse command-line options and positional arguments:
    parsed_args = parser.parse_args(args=args)
    # Avoid noisy boilerplate, functions meant to handle command-line usage should
    # accept kwargs that match the defined option and argument names:
    cli_kwargs = dict(vars(parsed_args))
    # Remove any meta options and arguments, those used to direct option and argument
    # handling:
    del cli_kwargs["command"]
    # Separate the arguments for the subcommand:
    prunerr_dests = {
        action.dest for action in parser._actions  # pylint: disable=protected-access
    }
    shared_kwargs = dict(cli_kwargs)
    command_kwargs = {}
    for dest, value in list(shared_kwargs.items()):
        if dest not in prunerr_dests:  # pragma: no cover
            command_kwargs[dest] = value
            del shared_kwargs[dest]

    # Configure logging for command-line usage:
    config_cli_logging(**shared_kwargs)
    shared_kwargs.pop("log_level", None)

    # Delegate to the function for the subcommand command-line argument:
    logger.debug("Running %r subcommand", parsed_args.command.__name__)
    # subcommands can return a result to pretty print, or handle output themselves and
    # return nothing:
    if (result := parsed_args.command(**command_kwargs)) is not None:
        json.dump(result, sys.stdout, indent=2)


main.__doc__ = __doc__
