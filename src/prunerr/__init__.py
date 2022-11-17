#!/usr/bin/env python
"""
Remove Servarr download client items to preserve disk space according to rules.
"""

import os
import os.path
import argparse
import subprocess
import logging
import pathlib  # TODO: replace os.path
import tempfile
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


class ServarrEventError(ValueError):
    """
    Download client state incorrect for Servarr event.
    """


class Prunerr:

    SEASON_EPISODE_TEMPLATE = (
        "S{episode[seasonNumber]:02d}E{episode[episodeNumber]:02d}"
    )

    # Prunerr constants
    PRUNERR_FILE_SUFFIXES = {".prunerr.json", "-servarr-imported.ln"}

    def __init__(self, config, servarrs, url, replay=False):
        """
        Do any config post-processing and set initial state.
        """
        self.url = url
        self.servarrs = servarrs

        # Downloader and Servarr client handling
        self.connect()
        session = self.client.get_session()

        # Prunerr config processing
        self.config = config

        # Download client config processing
        # Set any download client config defaults for Prunerr
        session_download_path = pathlib.Path(session.download_dir)
        self.config["downloaders"]["download-dir"] = pathlib.Path(
            self.config["downloaders"].get("download-dir", session_download_path)
        )
        self.config["downloaders"]["imported-dir"] = pathlib.Path(
            self.config["downloaders"].get(
                "imported-dir",
                session_download_path.parent / "imported",
            )
        )
        self.config["downloaders"]["deleted-dir"] = pathlib.Path(
            self.config["downloaders"].get(
                "deleted-dir",
                session_download_path.parent / "deleted",
            )
        )

        # Servarr API client and download client settings
        # Derive the destination directories for this download client for each type of
        # Servarr instance, e.g. `tvDirectory` vs `movieDirectory`.
        for servarr_config in self.servarrs.values():
            servarr_config["downloadDir"] = pathlib.Path(
                servarr_config["downloadclient"]["fieldValues"][
                    self.SERVARR_TYPE_MAPS[servarr_config["type"]]["download_dir_field"]
                ]
            ).resolve()
            if (
                self.config["downloaders"]["download-dir"]
                not in (servarr_config["downloadDir"] / "child").parents
            ):
                # TODO: Should this just be a logged error?
                raise ValueError(
                    f"Download client directory in Servarr settings, "
                    f"{str(servarr_config['downloadDir'])!r}, must be a descendant of "
                    f"the download client's default download directory, "
                    f"{str(servarr_config['downloadDir'])!r}"
                )
            servarr_config["importedDir"] = (
                self.config["downloaders"]["imported-dir"]
                / servarr_config["downloadDir"].relative_to(
                    self.config["downloaders"]["download-dir"],
                )
            ).resolve()
            servarr_config["deletedDir"] = (
                self.config["downloaders"]["deleted-dir"]
                / servarr_config["downloadDir"].relative_to(
                    self.config["downloaders"]["download-dir"],
                )
            ).resolve()

        # Should all events be handled again, even if previously processed.
        self.replay = replay

        # Initial state
        self.quiet = False
    def select_imported_download_id(self, servarr_history, source_title):
        """
        Return the first download client item ID from imported events.
        """
        if source_title not in servarr_history["event_types"]["source_titles"]:
            logger.warning(
                "Import not found in Servarr history: %s",
                source_title,
            )
            return
        imported_events = servarr_history["event_types"]["source_titles"][source_title]
        if "downloadFolder_imported" not in imported_events:
            logger.warning(
                "No Servarr import history found: %s",
                source_title,
            )
            return
        for imported_record in imported_events["downloadFolder_imported"]:
            if "downloadId" in imported_record:
                return imported_record["downloadId"].lower()
        logger.warning(
            "No Servarr grabbed history found, "
            "could not match to download client item: %s",
            source_title,
        )

    def reimport_seeding(self):
        """
        Re-import all seeding torrents managed by the `daemon` command.

        Move all imported torrents back to the downloads directory so they can be
        re-importied (or re-copied).  Useful to recover from any remote data loss as
        much as is still possible with what torrents are still local.
        """
        self.update()
        session = self.client.get_session()

        for torrent in self.torrents:
            if torrent.status != "seeding" or torrent.downloadDir.startswith(
                session.download_dir
            ):
                continue

            self.move_torrent(
                torrent,
                old_path=self.config["downloaders"].get(
                    "imported-dir",
                    os.path.join(os.path.dirname(session.download_dir), "imported"),
                ),
                new_path=session.download_dir,
            )

    def restore_data(self):
        """
        Match torrent locations to matching paths with the largest size.

        Useful when torrents end up with different locations than their data.
        """
        session = self.client.get_session()
        incomplete_path = pathlib.Path(session.incomplete_dir)
        client_download_path = pathlib.Path(session.download_dir)
        restored_items = {}
        # Cache history paging across download items
        for servarr_config in self.servarrs.values():
            servarr_config["history"] = {}

        # Start by matching to any orphan paths
        orphans = self.find_orphans()
        # Start with the largest orphan path first
        orphans.reverse()
        for download_item in self.torrents:
            if download_item.status.lower().startswith("check"):
                logger.debug(
                    "Skipping verifying item: %r",
                    download_item,
                )
                continue
            download_id = download_item.hashString.lower()
            download_path = self.get_item_path(download_item)

            # Look for orphan paths that match by basename
            for orphan_size, orphan_path in orphans:
                orphan_path = pathlib.Path(orphan_path)
                if orphan_path.name == download_path.name:

                    # Largest orphan path whose basename matches
                    if orphan_path != download_path and (
                        # Avoid restoring partial data from item's that started
                        # re-downloading after the data was disconnected.  Only use
                        # orphans from the download client's incomplete or downloads
                        # directories the item's download directory doesn't exist.
                        not download_path.exists()
                        or (
                            incomplete_path not in orphan_path.parents
                            and client_download_path not in orphan_path.parents
                        )
                    ):
                        logger.info(
                            "Restoring data: %r -> %r",
                            str(download_path),
                            str(orphan_path),
                        )
                        download_item.locate_data(str(orphan_path.parent))
                        # Collect results of actions taken
                        restored_items.setdefault(download_item.name, {}).setdefault(
                            "orphans",
                            [],
                        ).append(str(orphan_path))
                        # Update local, in-memory data
                        download_item.update()
                        download_path = self.get_item_path(download_item)

                    # Found the largest matching path, no need to continue
                    break

            # Next try to restore as much as possible from the Servarr history
            for servarr_config in self.servarrs.values():
                servarr_history = servarr_config.setdefault("history", {})
                self.find_latest_item_history(
                    servarr_config,
                    torrent=download_item,
                )
                item_history = servarr_history["records"]["download_ids"].get(
                    download_id,
                    [],
                )
                if not item_history:
                    continue
                latest_record = item_history[0]

                # Restore Servarr download paths
                event_locations = self.SERVARR_EVENT_LOCATIONS[
                    latest_record["eventType"]
                ]
                dst_path = servarr_config[event_locations["dst"]]
                if download_path.parent != dst_path:
                    logger.info(
                        "Restoring download path: %r -> %r",
                        str(download_path),
                        str(dst_path),
                    )
                    new_download_path = self.move_torrent(
                        download_item,
                        download_path.parent,
                        dst_path,
                    )
                    # Collect results of actions taken
                    restored_items.setdefault(download_item.name, {}).setdefault(
                        "paths",
                        [],
                    ).append(str(new_download_path))
                    # Update local, in-memory data
                    download_item.update()
                    download_path = self.get_item_path(download_item)

                # Restore Servarr imports hard links
                # TODO: Honor Servarr hard link vs copy setting
                for imported_record in item_history:
                    if "importedPath" not in imported_record["data"]:
                        continue
                    imported_path = pathlib.Path(
                        imported_record["data"]["importedPath"],
                    )
                    if imported_path.exists():
                        item_root_name = self.get_item_root_name(download_item)
                        dropped_path = pathlib.Path(
                            imported_record["data"]["droppedPath"],
                        )
                        if item_root_name in dropped_path.parts:
                            relative_path = pathlib.Path(
                                *dropped_path.parts[
                                    dropped_path.parts.index(item_root_name) :
                                ]
                            )
                        else:
                            logger.error(
                                "Servarr dropped path doesn't include item root name: "
                                "%r",
                                str(dropped_path),
                            )

                        # Does the imported file correspond to a file in the download
                        # item.  If the imported file was extracted from an archive in
                        # the download item, for example, skip verifying and resuming.
                        imported_item_file = None
                        for item_file in download_item.files():
                            if item_file.name == str(relative_path):
                                imported_item_file = item_file
                                break

                        current_dropped_path = dst_path / relative_path
                        if imported_item_file is not None and (
                            not current_dropped_path.is_file()
                            or current_dropped_path.stat().st_nlink <= 1
                        ):
                            # Collect results of actions taken
                            restored_items.setdefault(
                                download_item.name,
                                {},
                            ).setdefault("imported", []).append(
                                str(imported_path),
                            )
                            if current_dropped_path.exists():
                                logger.info(
                                    "Removing dropped path: %r",
                                    str(current_dropped_path),
                                )
                                current_dropped_path.unlink()
                            elif not current_dropped_path.parent.exists():
                                logger.info(
                                    "Creating dropped directory: %r",
                                    str(current_dropped_path.parent),
                                )
                                current_dropped_path.parent.mkdir(
                                    parents=True,
                                    exist_ok=True,
                                )
                            logger.info(
                                "Restoring imported path: %r -> %r",
                                str(imported_path),
                                str(current_dropped_path),
                            )
                            imported_path.link_to(current_dropped_path)

                # Found corresponding Servarr history, stop iterating over Servarr
                # instances
                break
            else:
                logger.warning("No Servarr history found: %r", download_item)

        return restored_items


Prunerr.__doc__ = __doc__


def get_home():
    try:
        # Don't rely on os.environ['HOME'] such as under cron jobs
        import pwd

        return pwd.getpwuid(os.getuid()).pw_dir
    except ImportError:
        # Windows
        return os.path.expanduser("~")


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


def restore_data(prunerr, *args, **kwargs):
    prunerr.update()
    return prunerr.restore_data(*args, **kwargs)


restore_data.__doc__ = Prunerr.restore_data.__doc__
parser_restore_data = subparsers.add_parser(
    "restore-data",
    help=restore_data.__doc__.strip(),
    description=restore_data.__doc__.strip(),
)
parser_restore_data.set_defaults(command=restore_data)


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
        parsed_args.command.__name__,
    )
    results = parsed_args.command(runner, **command_kwargs)
    if results:
        pprint.pprint(results, sort_dicts=False)


main.__doc__ = __doc__
