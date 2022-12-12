"""
Remove Servarr download client items to preserve disk space according to rules.
"""

import os
import contextlib
import logging
import pathlib  # TODO: replace os.path
import argparse
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
# Define CLI sub-commands
subparsers = parser.add_subparsers(
    dest="command",
    required=True,
    help="sub-command",
)


def verify(runner, *args, **kwargs):  # pylint: disable=missing-function-docstring
    runner.update()
    runner.verify(*args, **kwargs)
    # Wait for all verifying torrents to finish when doing a single `verify` run.
    return runner.resume_verified_items(wait=True)


verify.__doc__ = prunerr.runner.PrunerrRunner.verify.__doc__
parser_verify = subparsers.add_parser(
    "verify",
    help=verify.__doc__.strip(),
    description=verify.__doc__.strip(),
)
parser_verify.set_defaults(command=verify)


def move(runner, *args, **kwargs):  # pylint: disable=missing-function-docstring
    runner.update()
    return runner.move(*args, **kwargs)


move.__doc__ = prunerr.runner.PrunerrRunner.move.__doc__
parser_move = subparsers.add_parser(
    "move",
    help=move.__doc__.strip(),
    description=move.__doc__.strip(),
)
parser_move.set_defaults(command=move)


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
    exec_results = runner.exec_(*args, **kwargs)

    # Wait for all verifying torrents to finish when doing a single `exec` run.
    resume_results = runner.resume_verified_items(wait=True)
    if resume_results:
        exec_results["verify"] = resume_results

    return exec_results


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
    logger.info("Running %r sub-command", parsed_args.command.__name__)
    # Sub-commands may return a result to be pretty printed, or handle output themselves
    # and return nothing.
    result = parsed_args.command(runner, **command_kwargs)
    if result is not None:
        pprint.pprint(result)


main.__doc__ = __doc__
