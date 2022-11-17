#!/usr/bin/env python
"""
Remove Servarr download client items to preserve disk space according to rules.
"""

import os
import os.path
import contextlib
import argparse
import logging
import pathlib  # TODO: replace os.path
import pprint
import mimetypes


import prunerr.runner
import prunerr.downloadclient

logger = logging.getLogger(__name__)

# Manage version through the VCS CI/CD process
__version__ = None
try:
    from . import version
except ImportError:  # pragma: no cover
    pass
else:  # pragma: no cover
    __version__ = version.version

# Add MIME types that may not be registered on all hosts
mimetypes.add_type("video/x-divx", ".divx")
mimetypes.add_type("text/x-nfo", ".nfo")


# Define command line options and arguments
parser = argparse.ArgumentParser(
    description=__doc__.strip(),
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
parser.add_argument(
    "--config",
    "-c",
    type=argparse.FileType("r"),
    default=str(pathlib.Path.home() / ".config" / "prunerr.yml"),
    help="""\
The path to the Prunerr configuration file. Example:
https://gitlab.com/rpatterson/prunerr/-/blob/master/src/prunerr/home/.config/prunerr.yml\
""",
)
parser.add_argument(
    "--replay",
    "-r",
    action="store_true",
    help="""\
Also run operations for Servarr events/history that have previously been run.
""",
)
# Define CLI sub-commands
subparsers = parser.add_subparsers(
    dest="command",
    required=True,
    help="sub-command",
)


def review(runner, *args, **kwargs):  # pylint: disable=missing-function-docstring
    runner.update()
    return runner.review(*args, **kwargs)


review.__doc__ = prunerr.runner.PrunerrRunner.review.__doc__
parser_review = subparsers.add_parser(
    "review",
    help=review.__doc__.strip(),
    description=review.__doc__.strip(),
)
# Make the function for the sub-command specified in the CLI argument available in the
# argument parser for delegation below.
parser_review.set_defaults(command=review)


def sync_(runner, *args, **kwargs):  # pylint: disable=missing-function-docstring
    runner.update()
    return runner.sync(*args, **kwargs)


sync_.__doc__ = prunerr.runner.PrunerrRunner.sync.__doc__
parser_sync = subparsers.add_parser(
    "sync",
    help=sync_.__doc__.strip(),
    description=sync_.__doc__.strip(),
)
parser_sync.set_defaults(command=sync_)


def free_space(runner, *args, **kwargs):  # pylint: disable=missing-function-docstring
    runner.update()
    return runner.free_space(*args, **kwargs)


free_space.__doc__ = prunerr.runner.PrunerrRunner.free_space.__doc__
parser_free_space = subparsers.add_parser(
    "free-space",
    help=free_space.__doc__.strip(),
    description=free_space.__doc__.strip(),
)
parser_free_space.set_defaults(command=free_space)


def exec_(runner, *args, **kwargs):  # pylint: disable=missing-function-docstring
    runner.update()
    return runner.exec_(*args, **kwargs)


exec_.__doc__ = prunerr.runner.PrunerrRunner.exec_.__doc__
parser_exec = subparsers.add_parser(
    "exec",
    help=exec_.__doc__.strip(),
    description=exec_.__doc__.strip(),
)
parser_exec.set_defaults(command=exec_)


def daemon(runner, *args, **kwargs):  # pylint: disable=missing-function-docstring
    return runner.daemon(*args, **kwargs)


daemon.__doc__ = prunerr.runner.PrunerrRunner.daemon.__doc__
parser_daemon = subparsers.add_parser(
    "daemon",
    help=daemon.__doc__.strip(),
    description=daemon.__doc__.strip(),
)
parser_daemon.set_defaults(command=daemon)


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
    }:
        level = logging.DEBUG
    else:  # pragma: no cover
        level = logging.INFO
    logger.setLevel(level)

    # Avoid logging all JSON responses, particularly the very large history responses
    # from Servarr APIs
    logging.getLogger("arrapi.api").setLevel(logging.INFO)

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
    # Use `argparse` to validate that the config file exists and can be read, then pass
    # the path into the runner.
    with contextlib.closing(cli_kwargs["config"]):
        cli_kwargs["config"] = cli_kwargs["config"].name
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

    runner = prunerr.runner.PrunerrRunner(**shared_kwargs)
    # Delegate to the function for the sub-command CLI argument
    logger.debug(
        "Running %r sub-command",
        parsed_args.command.__name__.strip("_"),
    )
    results = parsed_args.command(runner, **command_kwargs)
    if results:
        pprint.pprint(results, sort_dicts=False)


main.__doc__ = __doc__
