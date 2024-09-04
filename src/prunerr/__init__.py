# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

# PYTHON_ARGCOMPLETE_OK

"""
Remove Servarr download client items to preserve disk space according to rules.
"""

import sys
import typing
import contextlib
import logging
import pathlib  # TODO: replace os.path
import argparse
import re
import mimetypes
import json
import pdb

import argcomplete

import prunerr.runner
import prunerr.downloadclient
import prunerr.downloaditem
import prunerr.operations
import prunerr.servarr
from . import utils

logger = logging.getLogger(__name__)

# Manage version through the VCS CI/CD process
__version__ = None
try:
    from . import version
except ImportError:  # pragma: no cover
    pass
else:
    __version__ = version.version

# Add MIME types that may not be registered on all hosts
mimetypes.add_type("video/x-divx", ".divx")
mimetypes.add_type("text/x-nfo", ".nfo")

API_DOCSTRING_RE = re.compile("^ *:[^:]+: ", re.MULTILINE)


def strip_api_docstring(docstring: typing.Optional[str]) -> str:
    """
    Strip trailing API documentation reST field lists from docstrings if present.

    :param docstring: The ``__doc__`` including API documentation field lists.
    :return: The docstring without API documentation field lists.
    :raises ValueError: Something is wrong with the ``docstring``.
    """
    if docstring is None:  # pragma: no cover
        raise ValueError("Missing docstring")
    if (api_docstring_match := API_DOCSTRING_RE.search(docstring)) is None:
        return docstring
    return docstring[: api_docstring_match.start(0)]


# Define command line options and arguments
parser = argparse.ArgumentParser(
    description=strip_api_docstring(__doc__),
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
parser.add_argument(
    "--log-level",
    default=argparse.SUPPRESS,
    # The `logging` module provides no public access to all defined levels:
    choices=logging._nameToLevel,  # pylint: disable=protected-access
    help="Select logging verbosity. (default: INFO)",
)
parser.add_argument(
    "--config",
    "-c",
    type=argparse.FileType("r"),
    default=str(pathlib.Path.home() / ".config" / "prunerr.yml"),
    help="""\
The path to the Prunerr configuration file. Example:
https://gitlab.com/rpatterson/prunerr/-/blob/main/src/prunerr/home/.config/prunerr.yml\
""",
)
# Define command-line subcommands:
subparsers = parser.add_subparsers(
    dest="command",
    required=True,
    help="subcommand",
)


def verify(  # pylint: disable=missing-function-docstring,missing-return-doc
    runner,
    *args,
    **kwargs,
) -> dict:
    runner.update()
    verify_results = runner.verify(*args, **kwargs)
    # Wait for all verifying torrents to finish when doing a single `verify` run.
    runner.resume_verified_items(wait=True)
    return verify_results


verify.__doc__ = strip_api_docstring(prunerr.runner.PrunerrRunner.verify.__doc__)
parser_verify = subparsers.add_parser(
    "verify",
    help=str(verify.__doc__.strip()),
    description=str(verify.__doc__.strip()),
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
parser_verify.set_defaults(command=verify)


def move(  # pylint: disable=missing-function-docstring,missing-return-doc
    runner,
    *args,
    **kwargs,
) -> dict:
    runner.update()
    return runner.move(*args, **kwargs)


move.__doc__ = prunerr.runner.PrunerrRunner.move.__doc__
parser_move = subparsers.add_parser(
    "move",
    help=str(move.__doc__).strip(),
    description=str(move.__doc__).strip(),
)
parser_move.set_defaults(command=move)


def review(  # pylint: disable=missing-function-docstring,missing-return-doc
    runner,
    *args,
    **kwargs,
) -> dict:
    runner.update()
    return runner.review(*args, **kwargs)


review.__doc__ = prunerr.runner.PrunerrRunner.review.__doc__
parser_review = subparsers.add_parser(
    "review",
    help=str(review.__doc__).strip(),
    description=str(review.__doc__).strip(),
)
# Make the function for the sub-command specified in the CLI argument available in the
# argument parser for delegation below.
parser_review.set_defaults(command=review)


def free_space(  # pylint: disable=missing-function-docstring,missing-return-doc
    runner,
    *args,
    **kwargs,
) -> dict:
    runner.update()
    return runner.free_space(*args, **kwargs)


free_space.__doc__ = prunerr.runner.PrunerrRunner.free_space.__doc__
parser_free_space = subparsers.add_parser(
    "free-space",
    help=str(free_space.__doc__).strip(),
    description=str(free_space.__doc__).strip(),
)
parser_free_space.set_defaults(command=free_space)


def export(  # pylint: disable=missing-function-docstring,missing-return-doc
    runner,
    *args,
    **kwargs,
) -> dict:
    runner.update()
    return runner.export(*args, **kwargs)


export.__doc__ = prunerr.runner.PrunerrRunner.export.__doc__
parser_export = subparsers.add_parser(
    "export",
    help=str(export.__doc__).strip(),
    description=str(export.__doc__).strip(),
)
parser_export.set_defaults(command=export)


def re_add(  # pylint: disable=missing-function-docstring,missing-return-doc
    runner,
    *args,
    **kwargs,
) -> dict:
    runner.update()
    return runner.re_add(*args, **kwargs)


re_add.__doc__ = prunerr.runner.PrunerrRunner.re_add.__doc__
parser_re_add = subparsers.add_parser(
    "re-add",
    help=str(re_add.__doc__).strip(),
    description=str(re_add.__doc__).strip(),
)
parser_re_add.set_defaults(command=re_add)


def exec_(  # pylint: disable=missing-function-docstring,missing-return-doc
    runner,
    *args,
    **kwargs,
) -> typing.Optional[dict]:
    runner.update()
    results = {}
    if (exec_results := runner.exec_(*args, **kwargs)) is not None:
        results.update(exec_results)

    # Wait for all verifying torrents to finish when doing a single `exec` run.
    if resume_results := runner.resume_verified_items(wait=True):
        results["verify"] = resume_results

    if results:
        return results
    return None  # pragma: no cover


exec_.__doc__ = prunerr.runner.PrunerrRunner.exec_.__doc__
parser_exec = subparsers.add_parser(
    "exec",
    help=str(exec_.__doc__).strip(),
    description=str(exec_.__doc__).strip(),
)
parser_exec.set_defaults(command=exec_)


def daemon(runner, *args, **kwargs):  # pylint: disable=missing-function-docstring
    if utils.ntfy is not None:  # pragma: no cover
        logger.addHandler(utils.notify_handler)
    runner.daemon(*args, **kwargs)


daemon.__doc__ = prunerr.runner.PrunerrRunner.daemon.__doc__
parser_daemon = subparsers.add_parser(
    "daemon",
    help=str(daemon.__doc__).strip(),
    description=str(daemon.__doc__).strip(),
)
parser_daemon.set_defaults(command=daemon)
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
        if utils.DEBUG:
            log_level = "DEBUG"  # pragma: no cover
    logger.setLevel(getattr(logging, log_level.strip().upper()))
    # Log a given message only once per daemon session, the first loop.
    logger.addFilter(utils.daemon_once_filter)
    logging.getLogger(prunerr.runner.__name__).addFilter(
        utils.daemon_once_filter,
    )
    logging.getLogger(prunerr.downloadclient.__name__).addFilter(
        utils.daemon_once_filter,
    )
    logging.getLogger(prunerr.downloaditem.__name__).addFilter(
        utils.daemon_once_filter,
    )
    logging.getLogger(prunerr.operations.__name__).addFilter(
        utils.daemon_once_filter,
    )
    logging.getLogger(prunerr.servarr.__name__).addFilter(
        utils.daemon_once_filter,
    )

    # Avoid logging all JSON responses, particularly the very large history responses
    # from Servarr APIs
    logging.getLogger("arrapi.api").setLevel(logging.INFO)


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
    parsed_args = argparse.Namespace()
    try:
        parsed_args = parser.parse_args(args=args, namespace=parsed_args)
    finally:
        # Use `argparse` to validate that the config file exists and can be read, then
        # pass the path into the runner:
        if callable(getattr(parsed_args.config, "close", None)):  # pragma: no cover
            with contextlib.closing(parsed_args.config):
                parsed_args.config = parsed_args.config.name
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

    runner = prunerr.runner.PrunerrRunner(**shared_kwargs)
    # Delegate to the function for the subcommand command-line argument:
    logger.debug("Running %r subcommand", parsed_args.command.__name__)
    # subcommands can return a result to pretty print, or handle output themselves and
    # return nothing:
    if (result := parsed_args.command(runner, **command_kwargs)) is not None:
        json.dump(result, sys.stdout, indent=2)


main.__doc__ = __doc__
