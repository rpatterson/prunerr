#!/usr/bin/env python
"""
Remove Servarr download client items to preserve disk space according to rules.
"""

import os
import os.path
import argparse
import itertools
import socket
import shutil
import subprocess
import time
import logging
import pathlib  # TODO: replace os.path
import tempfile
import glob
import pprint
import json
import re
import mimetypes
import string

import yaml

import arrapi

import transmission_rpc
import transmission_rpc.utils
from transmission_rpc import error

import prunerr.runner
import prunerr.downloadclient

missing_value = object()

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


def yaml_arg_type(arg):
    return yaml.safe_load(argparse.FileType("r")(arg))


# Define command line options and arguments
parser = argparse.ArgumentParser(
    description=__doc__.strip(),
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
parser.add_argument(
    "--config",
    "-c",
    type=yaml_arg_type,
    default=str(pathlib.Path.home() / ".config" / "prunerr.yml"),
    help="""\
The path to the Prunerr configuration file. Example:
https://gitlab.com/rpatterson/prunerr/-/blob/master/home/.config/prunerr.yml\
""",
)
parser.add_argument(
    "--servarr-name",
    "-n",
    help="""\
The name of the Sonarr config within the Prunerr config.
Only applicable to certain sub-commands.\
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


def log_rmtree_error(function, path, excinfo):
    logger.error(
        "Error removing %r (%s)",
        path,
        ".".join((function.__module__, function.__name__)),
        exc_info=excinfo,
    )


class ServarrEventError(ValueError):
    """
    Download client state incorrect for Servarr event.
    """


class Prunerr(object):

    SEASON_EPISODE_TEMPLATE = (
        "S{episode[seasonNumber]:02d}E{episode[episodeNumber]:02d}"
    )

    # Prunerr constants
    PRUNERR_FILE_SUFFIXES = {".prunerr.json", "-servarr-imported.ln"}

    def __init__(self, config, servarrs, url, servarr_name=None, replay=False):
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
        self.config["downloaders"]["min-download-free-space"] = (
            (
                self.config["downloaders"]["max-download-bandwidth"]
                # Convert bandwidth bits to bytes
                / 8
            )
            * (
                # Convert bandwidth MBps to Bps
                1024
                * 1024
            )
            * (
                # Multiply by seconds of download time margin
                self.config["downloaders"].get("min-download-time-margin", 3600)
            )
        )
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

        # Indexers config processing
        self.indexer_operations = {
            operations_type: {
                indexer_config["name"]: indexer_config
                for indexer_config in indexer_configs
            }
            for operations_type, indexer_configs in config.get("indexers", {}).items()
            if operations_type != "urls"
        }

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
        self.servarr_name = servarr_name
        if servarr_name is not None:
            self.servarr_config = servarr_config = self.servarrs[servarr_name]
            if "client" not in servarr_config:
                self.servarr_config["client"] = self.SERVARR_TYPE_MAPS[
                    servarr_config["type"]
                ]["client"](
                    servarr_config["url"],
                    servarr_config["api-key"],
                )

        # Should all events be handled again, even if previously processed.
        self.replay = replay

        # Initial state
        self.popen = self.copying = None
        self.corrupt = {}
        self.quiet = False

    def exec_(self):
        """
        Prune download client items once.
        """
        # TODO: Audit the rest of the operations and decide which to keep and which to
        #       remove.
        session = self.client.get_session()
        session.download_dir = session.download_dir.strip(" `'\"")

        if self.config["downloaders"].get("readd-missing-data"):
            # Workaround an issue with Transmission when starting torrents with no free
            # space.
            self.readd_missing_data()

        # Keep track of torrents being verified to resume them
        # when verification is complete
        for torrent_id, torrent in list(self.corrupt.items()):
            try:
                torrent.update()
            except KeyError as exc:
                logger.error(
                    "Error updating corrupt %s, " "may have been removed: %s",
                    torrent,
                    exc,
                )
                del self.corrupt[torrent_id]
            else:
                if not torrent.status.startswith("check"):
                    logger.info("Resuming verified torrent: %s", torrent)
                    torrent.start()
                    torrent.update()
                    del self.corrupt[torrent_id]
        if self.corrupt:
            logger.info(
                "Waiting for torrents to verify:\n%s",
                "\n".join(map(str, self.corrupt.values())),
            )
        self.corrupt.update(self.verify_corrupted())

        if self.config["downloaders"].get("copy"):
            # Launch copy of most optimal, fully downloaded torrent in the downloads
            # dir.
            self._exec_copy(session)

        if "reviews" in self.indexer_operations:
            # Perform any review operations
            self.review_items()

        # Free disk space if needed
        # TODO: Unify with `self.review_items()`?
        self.free_space()

    def _exec_copy(self, session):
        """
        Launch copy of most optimal, fully downloaded torrent in the downloads dir.
        """
        destination = self.config["downloaders"]["copy"]["destination"]
        command = self.config["downloaders"]["copy"]["command"]
        imported_dir = self.config["downloaders"]["imported-dir"]
        retry_codes = self.config["downloaders"]["copy"].get(
            "daemon-retry-codes",
            [10, 12, 20, 30, 35, 255],
        )
        to_copy = sorted(
            (
                torrent
                for torrent in self.torrents
                if torrent.status == "seeding"
                and not os.path.relpath(
                    torrent.downloadDir,
                    self.config["downloaders"]["download-dir"],
                ).startswith(os.pardir + os.sep)
            ),
            # 1. Copy lower priority torrents first so they may be deleted
            # first.
            # 2. Copy smaller torrents first to avoid huge torrents preventing
            # timely download of others.
            key=lambda item: (item.bandwidthPriority, item.totalSize),
        )
        if self.popen is not None:
            if self.popen.poll() is None:
                if not to_copy or self.copying.hashString == to_copy[0].hashString:
                    logger.info("Letting running copy finish: %s", self.copying)
                    to_copy = None
                else:
                    logger.info("Terminating running copy: %s", self.copying)
                    self.popen.terminate()
            elif self.popen.returncode == 0:
                # Copy process succeeded
                # Move a torrent preserving subpath and block until done.
                self.move_torrent(
                    self.copying, old_path=session.download_dir, new_path=imported_dir
                )
                if to_copy and self.copying.hashString == to_copy[0].hashString:
                    to_copy.pop(0)
                self.copying = None
                self.popen = None
            elif self.popen.returncode not in retry_codes:
                logger.error(
                    "Copy failed with return code %s, pausing %s",
                    self.popen.returncode,
                    self.copying,
                )
                try:
                    self.copying.stop()
                    self.copying.update()
                except KeyError:
                    logger.exception("Error pausing %s", self.copying)
                self.popen = None

        if to_copy:
            logger.info(
                "Enabling upload speed limit during copy: %s", session.speed_limit_up
            )
            self.client.set_session(speed_limit_up_enabled=True)
            logger.info("Copying torrent: %s", to_copy[0])
            self.popen = self.copy(to_copy[0], destination, command)
            self.copying = to_copy[0]
        elif self.popen is None:
            logger.info("Disabling upload speed limit while not copying")
            self.client.set_session(speed_limit_up_enabled=False)

    def copy(self, torrent, destination, command):
        """Launch the copy subprocess and return the popen object."""
        if self.config["downloaders"].get("copy"):
            raise ValueError("Cannot copy items without appropriate configuration")
        session = self.client.get_session()
        session.download_dir = session.download_dir.strip(" `'\"")
        relative = os.path.relpath(torrent.downloadDir, session.download_dir)

        # Use a temporary file to keep feeding the file list to the
        # subprocess from blocking us
        files = tempfile.TemporaryFile(mode="w")
        files.writelines(
            os.path.join(relative, subpath) + "\n"
            for subpath in self.list_torrent_files(torrent)
        )
        files.seek(0)

        popen_cmd = command + [session.download_dir, destination]
        logger.info("Launching copy command: %s", " ".join(popen_cmd))
        popen = subprocess.Popen(popen_cmd, stdin=files, text=True)

        return popen

    def daemon(self):
        """
        Prune download client items continuously.
        """
        # Log only once at the start messages that would be noisy if repeated for every
        # daemon poll loop.
        self.quiet = False
        while True:
            # Start the clock for the poll loop as early as possible to keep the inner
            # loop duration as accurate as possible.
            start = time.time()

            try:
                # Refresh the list of download items
                self.update()
                # Run the `exec` sub-command as the inner loop
                self.exec_()
            except (
                socket.error,
                error.TransmissionError,
                arrapi.exceptions.ConnectionFailure,
            ) as exc:
                logger.error(
                    "Connection error while updating from server: %s",
                    exc,
                )
                # Re-connect to external services and retry
                self.connect()
                continue
            else:
                # Don't repeat noisy messages from now on.
                self.quiet = True
            logger.debug("Sub-command `exec` completed in %ss", time.time() - start)

            # Wait for the next interval
            poll = (
                self.config["daemon"].get(
                    "poll",
                    60,
                )
                if self.config["daemon"]
                else 60
            )
            # Loop early if the copy process finishes early
            while (
                self.popen is None or self.popen.poll() is None
            ) and time.time() - start < poll:
                time.sleep(1)
            logger.debug("Sub-command `daemon` looping after %ss", time.time() - start)

    def sort_torrents_by_tracker(self, torrents):
        """
        Sort the given torrents according to the indexer priority operations.
        """
        return sorted(
            ((index, torrent) for index, torrent in enumerate(torrents)),
            # remove lowest priority and highest ratio first
            key=lambda item: self.exec_indexer_operations(item[1])[1],
            reverse=True,
        )

    def review_items(self):
        """
        Apply review operations to all download items.
        """
        # Collect all Servarr API download queue records
        queue_records = {}
        for servarr_config in self.servarrs.values():
            queue_page = None
            page_num = 1
            while queue_page is None or (page_num * 250) <= queue_page["totalRecords"]:
                logger.debug(
                    "Requesting %r Servarr queue page: %s",
                    servarr_config["name"],
                    page_num,
                )
                queue_page = servarr_config["client"]._raw._get(
                    "queue",
                    # Maximum Servarr page size
                    pageSize=250,
                    page=page_num,
                )
                for record in queue_page["records"]:
                    if "downloadId" not in record:
                        # Pending downloads
                        continue
                    elif record["downloadId"] in queue_records:
                        # Let config order dictate which queue record should win
                        continue
                    record["servarr_config"] = servarr_config
                    queue_records[record["downloadId"]] = record
                page_num += 1

        session = self.client.get_session()
        for download_item in self.torrents:
            item_path = self.get_item_path(download_item)
            if pathlib.Path(session.download_dir) not in item_path.parents:
                # Support exempting items from review, put them in a different location.
                # Only review items in the client's default download directory.
                logger.debug(
                    "Ignoring item not in default download dir: %r",
                    download_item,
                )
                continue
            try:
                self.review_item(queue_records, download_item)
            except Exception:
                logger.exception(
                    "Un-handled exception reviewing item: %r",
                    download_item,
                )
                if "DEBUG" in os.environ:
                    raise
                else:
                    continue

    def review_item(self, queue_records, download_item):
        """
        Apply review operations to this download item.
        """
        include, sort_key = self.exec_indexer_operations(
            download_item,
            operations_type="reviews",
        )
        indexer_idx = sort_key[0]
        sort_values = sort_key[1:]
        reviews_indxers = self.config.get("indexers", {}).get("reviews", [])
        indexer_config = reviews_indxers[indexer_idx]
        operation_configs = indexer_config.get("operations", [])

        download_id = download_item.hashString.upper()
        queue_record = queue_records.get(download_id, {})
        queue_id = queue_record.get("id")

        for operation_config, sort_value in zip(operation_configs, sort_values):
            if sort_value:
                # Sort value didn't match review operation requirements
                continue

            if operation_config.get("remove", False):
                logger.info(
                    "Removing download item per %r review: %r",
                    operation_config["type"],
                    download_item,
                )
                if queue_id is None:
                    if self.servarrs and not self.quiet:
                        logger.warning(
                            "Download item not in any Servarr queue: %r",
                            download_item,
                        )
                    self.client.remove_torrent(
                        download_item.hashString,
                        delete_data=True,
                    )
                else:
                    delete_params = dict(removeFromClient="true")
                    if operation_config.get("blacklist", False):
                        delete_params["blacklist"] = "true"
                    queue_record["servarr_config"]["client"]._raw._delete(
                        f"queue/{queue_id}",
                        **delete_params,
                    )
                self.move_timeout(download_item, download_item.downloadDir)
                # Avoid race conditions, perform no further operations on removed items
                continue

            if "change" in operation_config:
                logger.info(
                    "Changing download item per %r review for %r: %s",
                    operation_config["type"],
                    download_item,
                    json.dumps(operation_config["change"]),
                )
                self.client.change_torrent(
                    [download_item.hashString],
                    **operation_config["change"],
                )

        return include, sort_key

    def free_space(self):
        """
        If running out of disk space, delete some torrents until enough space is free.

        Delete from the following groups of torrents in order:
        - torrents no longer registered with the tracker
        - orphaned paths not recognized by the download client or its items
        - seeding torrents, that have been successfully imported
        """
        # Workaround some issues with leading and trailing characters in the default
        # download directory path
        session = self.client.get_session()
        session.download_dir = session.download_dir.strip(" `'\"")
        if self.free_space_maybe_resume():
            # There is already sufficient free disk space
            return None
        removed_torrents = []

        # Delete any torrents that have already been imported and are no longer
        # recognized by their tracker: e.g. when a private tracker removes a
        # duplicate/invalid/unauthorized torrent
        unregistered_torrents = self.find_unregistered()
        if unregistered_torrents:
            logger.error(
                "Deleting from %s seeding torrents no longer registered with tracker",
                len(unregistered_torrents),
            )
            removed_torrents.extend(
                self.free_space_remove_torrents(unregistered_torrents),
            )
            if self.free_space_maybe_resume():
                # There is now sufficient free disk space
                return removed_torrents

        # Remove orphans, smallest first until enough space is freed
        # or there are no more orphans
        orphans = self.find_orphans()
        if orphans:
            logger.error(
                "Deleting from %s orphans to free space",
                len(orphans),
            )
            removed_torrents.extend(
                self.free_space_remove_torrents(orphans),
            )
            if self.free_space_maybe_resume():
                # There is now sufficient free disk space
                return removed_torrents

        # Next remove seeding torrents whose media have been deleted from the Servarr
        # libraries
        deleted_torrents = self.find_deleted()
        if deleted_torrents:
            logger.error(
                "Deleting from %s seeding torrents deleted from the Servarr library",
                len(deleted_torrents),
            )
            removed_torrents.extend(
                self.free_space_remove_torrents(deleted_torrents),
            )
            if self.free_space_maybe_resume():
                # There is now sufficient free disk space
                return removed_torrents

        # TODO: Maybe handle multiple downloading torrents for the
        # same Servarr item such as when trying several to see which
        # ones actually have decent download speeds?

        logger.error(
            "Running out of space but no items can be removed: %0.2f %s",
            *transmission_rpc.utils.format_size(session.download_dir_free_space),
        )
        kwargs = dict(speed_limit_down=0, speed_limit_down_enabled=True)
        # TODO: Notification when downloading is paused
        logger.info("Stopping downloading: %s", kwargs)
        self.client.set_session(**kwargs)
        return removed_torrents

    def free_space_maybe_resume(self):
        """
        Determine if there's sufficient free disk space, resume downloading if paused.
        """
        session = self.client.get_session()
        total_remaining_download = sum(
            torrent.leftUntilDone
            for torrent in self.torrents
            if torrent.status == "downloading"
        )
        if total_remaining_download > session.download_dir_free_space:
            logger.debug(
                "Total size of remaining downloads is greater than the available free "
                "space: %0.2f %s > %0.2f %s",
                *(
                    transmission_rpc.utils.format_size(total_remaining_download)
                    + transmission_rpc.utils.format_size(
                        session.download_dir_free_space
                    )
                ),
            )
        if (
            session.download_dir_free_space
            >= self.config["downloaders"]["min-download-free-space"]
        ):
            logger.debug(
                "Sufficient free space to continue downloading: %0.2f %s >= %0.2f %s",
                *(
                    transmission_rpc.utils.format_size(session.download_dir_free_space)
                    + transmission_rpc.utils.format_size(
                        self.config["downloaders"]["min-download-free-space"],
                    )
                ),
            )
            self._resume_down(session)
            return True
        return False

    def free_space_remove_torrents(self, candidates):
        """
        Delete items from the candidates until the minimum free space margin is met.

        Items may be torrents from the download client API or tuples of size and
        filesystem path.
        """
        session = self.client.get_session()
        removed = []
        for candidate in candidates:
            if self.free_space_maybe_resume():
                # There is now sufficient free disk space
                return removed

            # Handle different argument types
            if isinstance(candidate, (tuple, list)):
                metric, candidate = candidate
            if isinstance(candidate, int):
                candidate = self.get_download_item(int)

            # Handle actual torrents recognized by the download client
            if isinstance(candidate, transmission_rpc.Torrent):
                self.exec_indexer_operations(candidate)
                logger.info(
                    "Deleting seeding %s to free space, "
                    "%0.2f %s + %0.2f %s: indexer=%s, priority=%s, ratio=%0.2f",
                    candidate,
                    *(
                        transmission_rpc.utils.format_size(
                            session.download_dir_free_space,
                        )
                        + transmission_rpc.utils.format_size(candidate.totalSize)
                        + (
                            self.lookup_item_indexer(candidate),
                            candidate.bandwidthPriority,
                            candidate.ratio,
                        )
                    ),
                )
                download_dir = candidate.downloadDir
                self.client.remove_torrent([candidate.hashString], delete_data=True)
                self.move_timeout(candidate, download_dir)
                # Transmission may fail to actually remove the files if the filesystem
                # has run out of space.
                # TODO: Manually delete files if timed out

            # Handle filesystem paths not recognized by the download client
            else:
                logger.info(
                    "Deleting %r to free space: " "%0.2f %s + %0.2f %s",
                    candidate,
                    *(
                        transmission_rpc.utils.format_size(
                            session.download_dir_free_space,
                        )
                        + transmission_rpc.utils.format_size(metric)
                    ),
                )
                if not os.path.islink(candidate) and os.path.isdir(candidate):
                    shutil.rmtree(candidate, onerror=log_rmtree_error)
                else:
                    os.remove(candidate)

            removed.append(candidate)

        if removed:
            # Update the list of torrents if we removed any
            self.update()
        return removed

    def find_unregistered(self):
        """
        Filter already imported torrents that are no longer recognized by their tracker.

        For example, when a private tracker removes a duplicate/invalid/unauthorized
        torrent.
        """
        return self.sort_torrents_by_tracker(
            torrent
            for torrent in self.torrents
            if (
                (
                    torrent.status == "downloading"
                    or self.config["downloaders"]["imported-dir"]
                    in self.get_item_path(torrent).parents
                )
                and torrent.error == 2
                and "unregistered torrent" in torrent.errorString.lower()
            )
        )

    def find_orphans(self):
        """
        Find paths in download client directories that don't correspond to an item.

        Iterate through all the paths managed by each download client in turn, check
        all paths within those directories against the download items known to the
        download client, and report all paths that are unknown to the download client.

        Useful to identify paths to delete when freeing disk space.  Returned sorted
        from paths that use the least disk space to the most.
        """
        # FIXME: Identify duplicate directories with different ancestors
        #        /media/Library/incomplete/Foo Bar
        #        /media/Library/Videos/Movies/Foo Bar
        session = self.client.get_session()
        download_dirs = (
            # Transmission's `incomplete` directory for incomplete, leeching torrents
            session.incomplete_dir,
            # Transmission's `downloads` directory for complete, seeding torrents
            session.download_dir,
            # The Prunerr directories that reflect the state of download items in
            # Servarr.
            str(self.config["downloaders"]["imported-dir"]),
            str(self.config["downloaders"]["deleted-dir"]),
        )
        # FIXME: Select all the but the last/latest in the Servarr lifecycle when there
        # are multiple orphans for the same item.

        # Assemble all directories whose descendants are torrents
        torrent_dirs = set()
        torrent_paths = set()
        unstarted_names = set()
        # Include the directories managed by the download client
        # so we know what dirs to descend into when looking for orphans
        for client_dir in (session.incomplete_dir, session.download_dir):
            client_ancestor, tail = os.path.split(client_dir + os.sep)
            while client_ancestor not in torrent_dirs or client_ancestor != os.sep:
                torrent_dirs.add(client_ancestor)
                client_ancestor, tail = os.path.split(client_ancestor)
        # Add the paths for each individual torrent
        for torrent in self.torrents:
            item_path = self.get_item_path(torrent)
            if item_path.exists():
                # Transmission's `downloads` directory for complete, seeding torrents
                torrent_paths.add(str(item_path))
            else:
                # Transmission's `incomplete` directory for incomplete, leeching
                # torrents
                torrent_paths.add(
                    os.path.join(
                        session.incomplete_dir,
                        self.get_item_root_name(torrent),
                    )
                )
            # Include the ancestors of the torrent's path
            # so we know what dirs to descend into when looking for orphans
            torrent_dir, tail = os.path.split(torrent.downloadDir + os.sep)
            while torrent_dir not in torrent_dirs or torrent_dir != os.sep:
                torrent_dirs.add(torrent_dir)
                torrent_dir, tail = os.path.split(torrent_dir)
            if torrent.progress == 0.0:
                unstarted_names.add(torrent.name)

        # Sort the orphans by total directory size
        # TODO Windows compatibility
        du_cmd = ["du", "-s", "--block-size=1", "--files0-from=-"]
        du = subprocess.Popen(
            du_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=0,
        )
        orphans = sorted(
            itertools.chain(
                *(
                    self._list_orphans(
                        session,
                        torrent_dirs,
                        torrent_paths,
                        unstarted_names,
                        du,
                        download_dir,
                    )
                    for download_dir in download_dirs
                    if pathlib.Path(download_dir).is_dir()
                )
            ),
            key=lambda orphan: int(orphan[0]),
        )
        du.stdin.close()

        if orphans:
            logger.error(
                "Found orphan paths unrecognized by download client:\n%s",
                "\n".join(
                    f"{orphan_size}\t{orphan_path}"
                    for orphan_size, orphan_path in orphans
                ),
            )

        return orphans

    def _list_orphans(
        self,
        session,
        torrent_dirs,
        torrent_paths,
        unstarted_names,
        du,
        path,
    ):
        """Recursively list paths that aren't a part of any torrent."""
        path = pathlib.Path(path)
        for entry_path in pathlib.Path(path).iterdir():
            # Don't consider Prunerr files with any other corresponding
            # files present to be orphans.
            is_prunerr_file = False
            for prunerr_suffix in self.PRUNERR_FILE_SUFFIXES:
                if entry_path.name.endswith(prunerr_suffix):
                    entry_base = entry_path.name[: -len(prunerr_suffix)]
                    for unstarted_name in unstarted_names:
                        if unstarted_name.startswith(entry_base):
                            is_prunerr_file = True
                            break
                    entry_glob = f"{glob.escape(entry_base)}*"
                    non_orphans = {
                        match_path
                        for match_path in itertools.chain(
                            pathlib.Path(session.incomplete_dir).glob(entry_glob),
                            entry_path.parent.glob(entry_glob),
                        )
                        if not {
                            match_path
                            for prunerr_suffix in self.PRUNERR_FILE_SUFFIXES
                            if match_path.name.endswith(prunerr_suffix)
                        }
                    }
                    if non_orphans:
                        is_prunerr_file = True
                        break
            if is_prunerr_file:
                continue

            if (
                str(entry_path) not in torrent_paths
                and str(entry_path) not in torrent_dirs
            ):
                du.stdin.write(f"{entry_path}\0")
                du_line = du.stdout.readline()
                size, du_path = du_line[:-1].split("\t", 1)[:2]
                size = int(size)
                yield (int(size), str(entry_path))
            elif str(entry_path) in torrent_dirs:
                for orphan in self._list_orphans(
                    session,
                    torrent_dirs,
                    torrent_paths,
                    unstarted_names,
                    du,
                    entry_path,
                ):
                    yield orphan

    def find_deleted(self):
        """
        Filter torrents that have been deleted from the Servarr library.
        """
        return self.sort_torrents_by_tracker(
            torrent
            for torrent in self.torrents
            # only those previously synced and moved
            if torrent.status == "seeding"
            and self.config["downloaders"]["deleted-dir"]
            in self.get_item_path(torrent).parents
            # TODO: Optionally include imported items for Servarr configurations that
            # copy items instead of making hard-links, such as when the download client
            # isn't on the same host as the Servarr instance
            and self.exec_indexer_operations(torrent)[0]
        )

    def lookup_item_indexer(self, torrent):
        """
        Lookup the indexer for this torrent and cache.
        """
        download_data = torrent.prunerr_data
        if "indexer" in download_data:
            return download_data["indexer"]
        download_path = self.get_item_path(torrent)

        indexer_name = None
        # Try to find an indexer name from the items Servarr history
        for servarr_config in self.servarrs.values():
            for servarr_dir in (
                servarr_config["downloadDir"],
                servarr_config["importedDir"],
                servarr_config["deletedDir"],
            ):
                if servarr_dir in download_path.parents:
                    break
            else:
                # Not managed by this servarr instance
                continue
            download_record = self.find_latest_item_history(
                servarr_config,
                torrent=torrent,
            )
            if download_record:
                if "indexer" in download_record["data"]:
                    indexer_name = download_record["data"]["indexer"]
                    break
                else:
                    logger.warning(
                        "No indexer found in Servarr history for download item: %r",
                        torrent,
                    )
        else:
            logger.debug(
                "No Servarr history found for download item: %r",
                torrent,
            )

        # Match by indexer URLs when no indexer name is available
        if not indexer_name:
            indexer_name = self.match_item_indexer_urls(torrent)

        download_data["indexer"] = indexer_name
        return indexer_name

    def exec_indexer_operations(self, torrent, operations_type="priorities"):
        """
        Run indexer operations for the download item and return results.
        """
        cached_results = vars(torrent).setdefault("prunerr_operations_results", {})
        if operations_type in cached_results:
            return cached_results[operations_type]

        indexer_configs = self.indexer_operations.get(operations_type, {})
        indexer_name = self.lookup_item_indexer(torrent)
        if indexer_name not in indexer_configs:
            indexer_name = None
        indexer_idx = list(indexer_configs.keys()).index(indexer_name)
        indexer_config = indexer_configs[indexer_name]

        include, sort_key = self.exec_operations(indexer_config["operations"], torrent)
        cached_results[operations_type] = (include, (indexer_idx,) + sort_key)
        return cached_results[operations_type]

    def exec_operations(self, operation_configs, torrent):
        """
        Execute each of the configured indexer priority operations
        """
        # TODO: Add `name` to operation configs and use in log/exc messages
        sort_key = []
        include = True
        for operation_config in operation_configs:
            executor = getattr(self, f"exec_operation_{operation_config['type']}", None)
            if executor is None:
                raise NotImplementedError(
                    f"No indexer priority operation executor found for type "
                    f"{operation_config['type']!r}"
                )
            # Delegate to the executor to get the operation value for this download item
            sort_value = executor(operation_config, torrent)
            if sort_value is None:
                # If an executor returns None, all other handling should be skipped
                sort_key.append(None)
                continue

            # Apply any restrictions that can apply across different operation types
            sort_bool = None
            if "equals" in operation_config:
                sort_bool = sort_value == operation_config["equals"]
                if "minimum" in operation_config or "maximum" in operation_config:
                    raise ValueError(
                        f"Operation {operation_config['type']!r} "
                        f"includes both `equals` and `minimum` or `maximum`"
                    )
            else:
                if "minimum" in operation_config:
                    sort_bool = sort_value >= operation_config["minimum"]
                if "maximum" in operation_config and (sort_bool is None or sort_bool):
                    sort_bool = sort_value <= operation_config["maximum"]
            if sort_bool is not None:
                sort_value = sort_bool
            # Should the operation value be used to filter this download item?
            if operation_config.get("filter", False) and include:
                include = bool(sort_value)
            # Should the operation value be reversed when ordering the download items?
            if operation_config.get("reversed", False):
                if isinstance(sort_value, (bool, int, float)):
                    sort_value = -sort_value
                elif isinstance(sort_value, (tuple, list, str)):
                    sort_value = reversed(sort_value)
                else:
                    raise NotImplementedError(
                        f"Indexer priority operation value doesn't support `reversed`:"
                        f"{sort_value!r}"
                    )
            sort_key.append(sort_value)
        return include, tuple(sort_key)

    def exec_operation_value(self, operation_config, torrent):
        """
        Return the attribute or key value for the download item.
        """
        # Use `missing_value` instead of `hasattr()`
        # to avoid redundant property method calls
        value = getattr(torrent, operation_config["name"], missing_value)
        if value is not missing_value:
            return value
        if callable(getattr(torrent, "get", None)):
            return torrent.get(operation_config["name"])

    def exec_operation_or(self, operation_config, torrent):
        """
        Return `True` if any of the nested operations return `True`.
        """
        include, sort_key = self.exec_operations(
            operation_config["operations"],
            torrent,
        )
        for sort_value in sort_key:
            if sort_value:
                return sort_value
        return sort_key[-1]

    def exec_operation_and(self, operation_config, download_item):
        """
        Return `False` if any of the nested operations return `False`.
        """
        include, sort_key = self.exec_operations(
            operation_config["operations"],
            download_item,
        )
        for sort_value in sort_key:
            if not sort_value:
                return sort_value
        return sort_key[-1]

    def exec_operation_files(self, operation_config, download_item):
        """
        Return aggregated values from item files.
        """
        file_attr = operation_config.get("name", "size")
        aggregation = operation_config.get("aggregation", "portion")
        total = operation_config.get("total", "size_when_done")

        item_files = download_item.files()
        self.seen_empty_files = getattr(self, "seen_empty_files", set())
        if not item_files:
            if download_item.hashString.upper() not in self.seen_empty_files:
                logger.debug(
                    "Download item contains no files: %r",
                    download_item,
                )
                self.seen_empty_files.add(download_item.hashString.upper())
            return False

        patterns = operation_config.get("patterns", [])
        if patterns:
            matching_files = []
            for pattern in patterns:
                matching_files.extend(
                    item_file
                    for item_file in item_files
                    if re.fullmatch(pattern, item_file.name)
                )
        else:
            matching_files = item_files

        if aggregation == "count":
            sort_value = len(matching_files)
        elif aggregation in {"sum", "portion"}:
            sort_value = sum(
                getattr(matching_file, file_attr) for matching_file in matching_files
            )
            if aggregation == "portion":
                sort_value = sort_value / getattr(download_item, total)
        else:
            raise ValueError(f"Unknown item files aggregation {aggregation!r}")

        return sort_value

    def _resume_down(self, session):
        """
        Resume downloading if it's been stopped.
        """
        speed_limit_down = self.config["downloaders"]["max-download-bandwidth"]
        if session.speed_limit_down_enabled and (
            not speed_limit_down or speed_limit_down != session.speed_limit_down
        ):
            if (
                self.config["downloaders"].get(
                    "resume-set-download-bandwidth-limit",
                    False,
                )
                and speed_limit_down
            ):
                kwargs = dict(speed_limit_down=speed_limit_down)
            else:
                kwargs = dict(speed_limit_down_enabled=False)
            logger.info("Resuming downloading: %s", kwargs)
            self.client.set_session(**kwargs)

    def verify_corrupted(self):
        """
        Verify any incomplete torrents that are paused because of corruption.
        """
        corrupt = dict(
            (torrent.hashString, torrent)
            for torrent in self.torrents
            if torrent.status == "stopped"
            and torrent.error == 3
            and (
                "verif" in torrent.errorString.lower()
                or "corrput" in torrent.errorString.lower()
            )
        )
        if corrupt:
            logger.info(
                "Verifying corrupt torrents:\n%s", "\n".join(map(str, corrupt.values()))
            )
            self.client.verify_torrent(list(corrupt.keys()))
            for torrent in corrupt.values():
                torrent.update()

        return corrupt

    def readd_item(self, download_item):
        """
        Re-add to transmission the `*.torrent` file for the item.
        """
        download_item = self.get_download_item(download_item.hashString)
        with open(download_item.torrentFile, mode="r+b") as download_item_opened:
            self.client.remove_torrent(ids=[download_item.hashString])
            readded = self.client.add_torrent(
                torrent=download_item_opened,
                # These are the only fields from the `add_torrent()` call signature
                # in the docs I could see corresponding fields for in the
                # representation of a torrent.
                bandwidthPriority=download_item.bandwidthPriority,
                download_dir=download_item.download_dir,
                peer_limit=download_item.peer_limit,
            )
        readded = self.get_download_item(readded.hashString)
        readded.update()
        assert readded.download_dir == download_item.download_dir, (
            f"Re-added download location changed: "
            f"{download_item.download_dir!r} -> {readded.download_dir!r}"
        )
        return readded

    def readd_missing_data(self):
        """
        Workaround an issue with Transmission when starting torrents with no free space.

        While there's no free space on the device, torrents for which no significant
        data has been downloaded will have no local files created (beyond the
        `./resume/*.resume` file).  When Transmission is later restarted after some
        space has been freed on the device, it will consider the "missing" local files
        an error but no actions can be taken to force it to create the local files anew
        and resume.  Not verifying, not moving, not re-adding the torrent without first
        removing it and certainly not simply resuming:

        https://github.com/transmission/transmission/issues/83

        Work around these issues by keeping the `./torrents/*.torrent` file open so that
        Transmission can't remove it, removing the torrent from Transmission, and
        re-adding the opened torrent file to Transmission.  There's no way I know of to
        distinguish between this very common case and other issues that may result in
        the same `No data found!` error message so there's a chance this can cause
        issues.
        """
        readded_items = []
        for torrent in self.torrents:
            if not (
                torrent.status == "stopped"
                and torrent.error == 3
                and torrent.errorString.lower().startswith("no data found")
            ):
                continue
            logger.error("No data found for %s, re-adding", torrent)
            try:
                readded = self.readd_item(torrent)
            except Exception:
                logger.exception(
                    "Un-handled exception re-adding item: %r",
                    torrent,
                )
                if "DEBUG" in os.environ:
                    raise
                else:
                    continue
            readded_items.append(readded)
        if readded_items:
            self.update()

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

    def get_download_item(self, download_id):
        """
        Get a download client item, tolerate missing items while logging the error.
        """
        if isinstance(download_id, str):
            download_id = download_id.lower()
        try:
            torrent = self.client.get_torrent(download_id)
            return prunerr.downloadclient.PrunerrDownloadItem(
                self,
                torrent._client,
                torrent,
            )
        except KeyError:
            # Can happen if the download client item has been manually deleted
            logger.error(
                "Could not find item in download client "
                "for Servarr imported event: %s",
                download_id,
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

            # Verify item data and resume if anything we've done or can check indicates
            # it might have been successfully restored.
            download_parent = pathlib.Path(download_item.download_dir)
            if (
                (
                    download_item.status == "stopped"
                    and download_parent != client_download_path
                )
                or restored_items.get(download_item.name, {}).get("orphans", [])
                or restored_items.get(download_item.name, {}).get("imported", [])
            ):
                logger.info(
                    "Verifying and resuming: %r",
                    download_item,
                )
                self.client.verify_torrent([download_item.hashString])
                download_item.start()

        return restored_items

    def relink(self):
        """
        Relink the source from the latest import history record if present.

        Useful something else has been linked over the destination, such as when an
        extra video video file with the same extenstion/suffix is imported.

        https://forums.sonarr.tv/t/importing-extra-files-overwrites-samples-over-full-video-files/30039/3
        """
        event_locations = self.SERVARR_EVENT_LOCATIONS["downloadFolderImported"]
        for servarr_config in self.servarrs.values():
            # Radarr movies or Sonarr series episodes, `movieId` vs `episodeId`
            item_id_field = (
                f"{self.SERVARR_TYPE_MAPS[servarr_config['type']]['item_type']}Id"
            )
            item_ids = set()
            # Prunerr lifecycle top-level directories
            downloads_dir = servarr_config[event_locations["src"]]
            imports_dir = servarr_config[event_locations["dst"]]

            # Page through all import history
            history_page = None
            history_page_num = 1
            while (
                # Is history for this Servarr instance exhausted?
                history_page is None
                or (history_page_num * 250) <= history_page["totalRecords"]
            ):
                logger.debug(
                    "Requesting %r Servarr history page: %s",
                    servarr_config["name"],
                    history_page_num,
                )
                history_page = servarr_config["client"]._raw._get(
                    "history",
                    # Only import history records
                    eventType=3,
                    # Most recent first
                    sortKey="date",
                    sortDirection="descending",
                    # Maximum Servarr page size
                    pageSize=250,
                    page=history_page_num,
                )
                history_page_num += 1

                # Check all import history records in this page
                for history_record in history_page["records"]:
                    item_id = history_record[item_id_field]
                    if item_id in item_ids:
                        logger.debug(
                            "Skipping older import history record: %r",
                            item_id,
                        )
                        continue
                    item_ids.add(item_id)
                    logger.debug(
                        "Processing item item: %r",
                        item_id,
                    )

                    imported_path = pathlib.Path(history_record["data"]["importedPath"])
                    if not imported_path.exists():
                        logger.warning(
                            "Skipping missing imported path: %s",
                            imported_path,
                        )
                        continue

                    # Checks and adjustments for Prunerr moves
                    dropped_path = pathlib.Path(history_record["data"]["droppedPath"])
                    if downloads_dir not in dropped_path.parents:
                        logger.warning(
                            "Skipping dropped path not in downloads: %s",
                            dropped_path,
                        )
                        continue
                    relative_path = dropped_path.relative_to(downloads_dir)
                    source_path = imports_dir / relative_path
                    if not source_path.exists():
                        logger.info(
                            "Downloaded source path not longer exists: %s",
                            source_path,
                        )
                        continue

                    source_stat = source_path.stat()
                    imported_stat = imported_path.stat()
                    if (source_stat.st_dev, source_stat.st_ino) == (
                        imported_stat.st_dev,
                        imported_stat.st_ino,
                    ):
                        logger.info(
                            "Source already linked to imported path: %s",
                            source_path,
                        )
                        continue

                    backup_path = imported_path.with_name(
                        f"{imported_path.name}.~prunerr-relink~"
                    )
                    if backup_path.exists():
                        logger.warning(
                            "Deleting previous backup: %s",
                            backup_path,
                        )
                        backup_path.unlink()
                    logger.debug(
                        "Backing up existing imported link: %s",
                        backup_path,
                    )
                    imported_path.rename(backup_path)

                    logger.info(
                        "Linking source to imported path: %s -> %s",
                        source_path,
                        imported_path,
                    )
                    source_path.link_to(imported_path)

    def rename(self, series_id, download_path):
        """
        Rename download item video files based on Sonarr episode titles.

        Useful to automate as much as possible the cleanup of download items whose
        naming or numbering scheme is wildly different from what Sonarr can handle.  Run
        this sub-command and then use Sonar's manual import UI to cleanup the rest.

        Best practice is to make a hard linked copy of the download item (`$ cp -alv
        ...`) in a temporary location on the same filesystem and run this sub-command on
        that temporary location.  This allows one to undo or redo the operation and also
        do further manual cleanup after the operation before importing.
        """
        # Normalize and map episode titles to episode data
        if not self.servarr_name:
            raise ValueError("The `--servar-name=...` option is required")
        servarr_type_map = self.SERVARR_TYPE_MAPS[self.servarr_config["type"]]
        params = {f"{servarr_type_map['dir_type']}Id": series_id}
        logger.debug(
            "Requesting %r Sonarr series title: %s",
            self.servarr_config["name"],
            json.dumps(params),
        )
        series = self.servarr_config["client"]._raw._get(f"series/{series_id}")
        series_title_str = normalize_str(series["title"])
        series_title_nlp = normalize_nlp(series["title"])
        logger.debug(
            "Requesting %r Sonarr episode titles: %s",
            self.servarr_config["name"],
            json.dumps(params),
        )
        episodes = self.servarr_config["client"]._raw._get("episode", **params)
        episode_titles_str = {}
        episode_titles_nlp = {}
        logger.info(
            "Normalizing %r Sonarr episode titles, may take some time: %s",
            self.servarr_config["name"],
            json.dumps(params),
        )
        for episode in episodes:
            episode["seasonEpisode"] = self.SEASON_EPISODE_TEMPLATE.format(
                episode=episode,
            )
            episode["seasonTitle"] = f"{episode['seasonEpisode']} - {episode['title']}"

            # Collect episode titles normalized using dumb string processing
            title_str = normalize_str(episode["title"])
            if title_str in series_title_str:
                logger.warning(
                    "String normalized episode title matches series title: %r ~ %r",
                    episode["seasonTitle"],
                    series["title"],
                )
            elif title_str in episode_titles_str:
                logger.warning(
                    "Duplicate string normalized episode title: %r ~ %r",
                    episode["seasonTitle"],
                    episode_titles_str[title_str]["seasonTitle"],
                )
                del episode_titles_str[title_str]
            else:
                episode_titles_str[title_str] = episode

            # Collect episode titles normalized using NLP
            title_nlp = normalize_nlp(episode["title"])
            if title_nlp in series_title_nlp:
                logger.warning(
                    "NLP normalized episode title matches series title: %r ~ %r",
                    episode["seasonTitle"],
                    series["title"],
                )
            elif title_nlp in episode_titles_nlp:
                logger.warning(
                    "Duplicate NLP normalized episode title: %r ~ %r",
                    episode["seasonTitle"],
                    episode_titles_nlp[title_nlp]["seasonTitle"],
                )
                del episode_titles_nlp[title_nlp]
            else:
                episode_titles_nlp[title_nlp] = episode

        # Walk through the video files
        logger.debug(
            "Walking download item video files: %s",
            download_path,
        )
        for video_path in download_path.glob("**/*.*"):
            video_type, _ = mimetypes.guess_type(video_path, strict=False)
            if video_type is None:
                logger.warning(
                    "Could not identify type: %s",
                    video_path,
                )
                continue
            video_major, _ = video_type.split("/", 1)
            if video_major.lower() != "video":
                logger.debug(
                    "Skipping non-video file: %s",
                    video_path,
                )
                continue

            # Compare normalized episode titles to the normalized file name
            logger.debug(
                "Comparing file name to episode titles: %s",
                video_path,
            )
            episode = None

            # Start with dumb normalization, just string processing
            name_str = normalize_str(video_path.stem)
            for title_str, episode in sorted(
                episode_titles_str.items(),
                # Longer matches first
                key=lambda item: len(item[0]),
                reverse=True,
            ):
                if title_str in name_str:
                    logger.debug(
                        "Matched string normalization for %r: %s",
                        episode["seasonTitle"],
                        str(video_path),
                    )
                    break

            # Next try smarter but less precise normalization using NLP
            else:
                name_nlp = normalize_nlp(video_path.stem)
                for title_nlp, episode in sorted(
                    episode_titles_nlp.items(),
                    # Longer matches first
                    key=lambda item: len(item[0]),
                    reverse=True,
                ):
                    if title_nlp in name_nlp:
                        logger.debug(
                            "Matched NLP normalization for %r: %s",
                            episode["seasonTitle"],
                            str(video_path),
                        )
                        break
                else:
                    logger.warning(
                        "No episode title match: %s",
                        str(video_path),
                    )
                    continue

            renamed_path = video_path.with_stem(
                servarr_type_map["rename_template"].format(
                    series=series,
                    episode=episode,
                ),
            )
            if renamed_path == video_path:
                logger.debug(
                    "Video file for %s already named correctly: %s",
                    episode["seasonEpisode"],
                    str(video_path),
                )
                continue
            else:
                logger.info(
                    "Renaming for %s: %r -> %r",
                    episode["seasonEpisode"],
                    str(video_path),
                    str(renamed_path),
                )
                video_path.rename(renamed_path)


Prunerr.__doc__ = __doc__


def get_home():
    try:
        # Don't rely on os.environ['HOME'] such as under cron jobs
        import pwd

        return pwd.getpwuid(os.getuid()).pw_dir
    except ImportError:
        # Windows
        return os.path.expanduser("~")


PUNCT_RE = re.compile("[\\{}]".format("\\".join(punct for punct in string.punctuation)))


def normalize_str(text):
    """
    Normalize text, such as media titles, into a minimal string for comparison.

    Uses dumb/naive normalization, mostly just stripping punctuation and redundant
    spaces.
    """
    # Normalize case
    text = text.lower()
    # Strip leading/trailing whitespace
    text = text.strip()
    # Strip out punctuation
    text = PUNCT_RE.sub("", text)
    # Cleanup redundant spaces
    while "  " in text:
        text = text.replace("  ", " ")
    # Strip out punctuation
    return text


NLP = None
STOP_WORDS = {"a", "an", "the", "and", "or", "of", "on", "to"}


def normalize_nlp(text):
    """
    Normalize text, such as media titles, into a minimal string for comparison.

    Uses natural language processing to remove stop words, normalize
    inflected/conjugated word forms, etc..
    """
    global NLP
    if NLP is None:
        import spacy

        NLP = spacy.load("en_core_web_sm")
        # Spacy's  default stop words are a bit too aggressive for this purpose
        NLP.Defaults.stop_words = {
            stop_word
            for stop_word in NLP.Defaults.stop_words
            # Do normalize apostrophe versions
            if "'" in stop_word or "‘" in stop_word or "’" in stop_word
            # Otherwise only strip out a small subset of stop workds
            or stop_word in STOP_WORDS
        }
    # Handling of possessive punctuation can result in confusion around plural forms
    doc = NLP(text.replace("'", ""))
    return " ".join(
        # Normalize case
        token.lemma_.lower()
        for token in doc
        # Strip out stop words, e.g.: the, a, etc.
        # Spacy considers numbers to be stop words, but numbers may be meaningful for
        # matching titles, e.g.: Foo Episode Part 1, Foo Episode Part 2, ...
        if (token.like_num or not token.is_stop)
        # Strip out punctuation and redundant spaces
        and not (token.is_punct or token.is_space)
    )


def sync_(runner, *args, **kwargs):  # pylint: disable=missing-function-docstring
    runner.connect()
    return runner.sync(*args, **kwargs)


sync_.__doc__ = prunerr.runner.PrunerrRunner.sync.__doc__
parser_sync = subparsers.add_parser(
    "sync",
    help=sync_.__doc__.strip(),
    description=sync_.__doc__.strip(),
)
# Make the function for the sub-command specified in the CLI argument available in the
# argument parser for delegation below.
parser_sync.set_defaults(command=sync_)


def exec_(runner, *args, **kwargs):  # pylint: disable=missing-function-docstring
    runner.connect()
    return runner.exec_(*args, **kwargs)


exec_.__doc__ = prunerr.runner.PrunerrRunner.exec_.__doc__
parser_exec = subparsers.add_parser(
    "exec",
    help=exec_.__doc__.strip(),
    description=exec_.__doc__.strip(),
)
# Make the function for the sub-command specified in the CLI argument available in the
# argument parser for delegation below.
parser_exec.set_defaults(command=exec_)


def daemon(prunerr, *args, **kwargs):
    return prunerr.daemon(*args, **kwargs)


daemon.__doc__ = Prunerr.daemon.__doc__
parser_daemon = subparsers.add_parser(
    "daemon",
    help=daemon.__doc__.strip(),
    description=daemon.__doc__.strip(),
)
# Make the function for the sub-command specified in the CLI argument available in the
# argument parser for delegation below.
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
# Make the function for the sub-command specified in the CLI argument available in the
# argument parser for delegation below.
parser_restore_data.set_defaults(command=restore_data)


def relink(prunerr, *args, **kwargs):
    prunerr.update()
    return prunerr.relink(*args, **kwargs)


relink.__doc__ = Prunerr.relink.__doc__
parser_relink = subparsers.add_parser(
    "relink",
    help=relink.__doc__.strip(),
    description=relink.__doc__.strip(),
)
# Make the function for the sub-command specified in the CLI argument available in the
# argument parser for delegation below.
parser_relink.set_defaults(command=relink)


def rename(prunerr, *args, **kwargs):
    prunerr.update()
    return prunerr.rename(*args, **kwargs)


rename.__doc__ = Prunerr.rename.__doc__
parser_rename = subparsers.add_parser(
    "rename",
    help=rename.__doc__.strip(),
    description=rename.__doc__.strip(),
)
parser_rename.add_argument(
    "series_id",
    type=int,
    help="""The DB ID of the Sonarr series whose episode titles to match.""",
)
parser_rename.add_argument(
    "download_path",
    type=pathlib.Path,
    help="""The path to the download item whose video files should be renamed.""",
)
# Make the function for the sub-command specified in the CLI argument available in the
# argument parser for delegation below.
parser_rename.set_defaults(command=rename)


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
        pprint.pprint(results)


main.__doc__ = __doc__
