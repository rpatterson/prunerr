"""
Python project structure foundation or template, top-level package.
"""

import os
import logging
import argparse
import pprint

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
# Define CLI sub-commands
subparsers = parser.add_subparsers(
    dest="command",
    required=True,
    help="sub-command",
)


def foobar(quiet=False):
    """
    Run the foobar sub-command from the command line.
    """
    if not quiet:
        return ["foo", "bar"]
    return None


parser_foobar = subparsers.add_parser(
    "foobar",
    help=foobar.__doc__.strip(),
    description=foobar.__doc__.strip(),
)
# Make the function for the sub-command specified in the CLI argument available in the
# argument parser for delegation below.
parser_foobar.set_defaults(command=foobar)
parser_foobar.add_argument(
    "-q",
    "--quiet",
    action="store_true",
    help="Suppress reporting results",
)


def config_cli_logging(
    root_level=logging.INFO, **kwargs
):  # pylint: disable=unused-argument
    """
    Configure logging CLI usage first, but also appropriate for writing to log files.
    """
    # Want just our logger's level, not others', to be controlled by options/environment
    logging.basicConfig(level=root_level)
    if "DEBUG" in os.environ and os.getenv("DEBUG").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:  # pragma: no cover
        level = logging.DEBUG
    else:
        level = logging.INFO
    logger.setLevel(level)
    return level


def main(args=None):  # pylint: disable=missing-function-docstring
    # Parse CLI options and positional arguments
    parsed_args = parser.parse_args(args=args)
    # Avoid noisy boilerplate, functions meant to handle CLI usage should accept kwargs
    # that match the defined option and argument names.
    cli_kwargs = dict(vars(parsed_args))
    # Remove any meta options and arguments, those used to direct option and argument
    # handling, that shouldn't be passed onto functions meant to handle CLI usage.  More
    # generally, err on the side of options and arguments being kwargs, remove the
    # exceptions.
    del cli_kwargs["command"]
    # Separate the arguments for the sub-command
    prunerr_dests = {
        action.dest for action in parser._actions  # pylint: disable=protected-access
    }
    shared_kwargs = dict(cli_kwargs)
    command_kwargs = {}
    for dest, value in list(shared_kwargs.items()):
        if dest not in prunerr_dests:  # pragma: no cover
            command_kwargs[dest] = value
            del shared_kwargs[dest]

    # Configure logging for CLI usage
    config_cli_logging(**shared_kwargs)

    # Delegate to the function for the sub-command CLI argument
    logger.info("Running %r sub-command", parsed_args.command.__name__)
    # Sub-commands may return a result to be pretty printed, or handle output themselves
    # and return nothing.
    result = parsed_args.command(**command_kwargs)
    if result is not None:
        pprint.pprint(result)


main.__doc__ = __doc__
