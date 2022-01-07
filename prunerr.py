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
import urllib
import tempfile
import glob
import pprint
import json
import datetime
import copy
import re

import ciso8601
import yaml

import arrapi

import transmission_rpc
from transmission_rpc import utils
from transmission_rpc import error

missing_value = object()

logger = logging.getLogger("prunerr")


def yaml_arg_type(arg):
    return yaml.safe_load(argparse.FileType("r")(arg))


parser = argparse.ArgumentParser(
    description=__doc__.strip(), formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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
subparsers = parser.add_subparsers(
    dest='command', required=True,
    help="sub-command help")


class TransmissionTimeout(Exception):
    """A transmission operation took too long."""


def splitpath(path, platform=os.path):
    """Split all path elements"""
    result = []
    head, tail = platform.split(path)
    result.append(tail)
    while head:
        head, tail = platform.split(head)
        result.append(tail or platform.sep)
        if not tail and head == platform.sep:
            break
    result.reverse()
    return result


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


class DownloadItem(transmission_rpc.Torrent):
    """
    Enrich download item data from the download client API.
    """

    def __init__(self, prunerr, client, torrent):
        """
        Reconstitute the native Python representation.
        """
        self.prunerr = prunerr

        fields = {
            field_name: field.value for field_name, field in torrent._fields.items()
        }
        super().__init__(client, fields)

    @property
    def prunerr_data(self):
        """
        Load the prunerr data file.
        """
        if "prunerr_data" in vars(self):
            return vars(self)["prunerr_data"]

        # Load the Prunerr data file
        download_path = self.prunerr.get_item_path(self)
        if download_path.is_file():
            data_path = download_path.with_suffix(".prunerr.json")
        else:
            data_path = download_path.with_name(f"{download_path.name}.prunerr.json")
        download_data = dict(path=data_path, history={})
        if not self.prunerr.replay and data_path.exists() and data_path.stat().st_size:
            with data_path.open() as data_opened:
                try:
                    download_data = json.load(data_opened)
                except Exception:
                    logger.exception("Failed to deserialize JSON file: %s", data_path)
            download_data["path"] = data_path
            if "latestImportedDate" in download_data:
                download_data["latestImportedDate"] = ciso8601.parse_datetime(
                    download_data["latestImportedDate"],
                )
            if download_data["history"] is None:
                logger.warning(
                    "No history previously found: %r",
                    self,
                )
                vars(self)["prunerr_data"] = download_data
                return download_data
            # Convert loaded JSON to native types where possible
            download_data["history"] = {
                ciso8601.parse_datetime(history_date):
                self.prunerr.deserialize_history(history_record)
                for history_date, history_record in
                download_data["history"].items()
            }

        # Cache the deserialized and normalized data
        vars(self)["prunerr_data"] = download_data
        return download_data

    @property
    def age(self):
        """
        The total time since the item was added.
        """
        return time.time() - self._fields["addedDate"].value

    @property
    def seconds_since_done(self):
        """
        Number of seconds elapsed since the torrent was completely downloaded.

        Best available estimation of total seeding time.
        """
        if (
            self._fields["leftUntilDone"].value
            or self._fields["percentDone"].value < 1
        ):
            logger.warning(
                "Can't determine seconds since done, not complete: %r",
                self,
            )
            return None
        done_date = self._fields["doneDate"].value
        if not done_date:
            # Try to find the latest imported record
            history_records = self.prunerr_data.get("history", {})
            for history_date in sorted(history_records, reverse=True):
                imported_record = history_records[history_date]
                if imported_record["eventType"] == "downloadFolderImported":
                    logger.warning(
                        "Missing done date for seconds since done"
                        ", using Servarr imported date: %r",
                        self,
                    )
                    done_date = imported_record["date"].timestamp()
                    break
            else:
                if self._fields["startDate"].value:
                    logger.warning(
                        "Missing done date for seconds since done"
                        ", using start date: %r",
                        self,
                    )
                    done_date = self._fields["startDate"].value
                elif self._fields["addedDate"].value:
                    logger.warning(
                        "Missing done date for seconds since done"
                        ", using added date: %r",
                        self,
                    )
                    done_date = self._fields["addedDate"].value
        if done_date and done_date > 0:
            return time.time() - done_date
        else:
            logger.warning(
                "Missing done date for seconds since done: %r",
                self,
            )
            return None

    @property
    def rate_total(self):
        """
        The total download rate across the whole download time.
        """
        done_date = self._fields["doneDate"].value
        if not done_date:
            done_date = time.time()
        return (
            self._fields["sizeWhenDone"].value - self._fields["leftUntilDone"].value
        ) / (
            done_date - self._fields["addedDate"].value
        )


class Prunerr(object):

    # Map the different Servarr applications type terminology
    SERVARR_TYPE_MAPS = dict(
        sonarr=dict(
            file_type="episode",
            dir_type="series",
            client=arrapi.SonarrAPI,
            download_dir_field="tvDirectory",
        ),
        radarr=dict(
            file_type="movie",
            dir_type="movie",
            client=arrapi.RadarrAPI,
            download_dir_field="movieDirectory",
        ),
    )
    # Map Servarr event types to download client location path config
    SERVARR_EVENT_LOCATIONS = dict(
        grabbed=dict(src="downloadDir", dst="downloadDir"),
        downloadFolderImported=dict(src="downloadDir", dst="importedDir"),
        downloadIgnored=dict(src="downloadDir", dst="deletedDir"),
        downloadFailed=dict(src="downloadDir", dst="deletedDir"),
        fileDeleted=dict(src="importedDir", dst="deletedDir"),
    )
    SERVARR_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
    # Number of seconds to wait for new file import history records to appear in Servarr
    # history.  This should be the maximum amount of time it might take to import a
    # single file in the download client item, not necessarily the entire item.  Imagine
    # how long might it take Sonarr to finish importing a download client item when:
    #
    # - Sonarr is configured to copy rather than making hard links
    # - the host running Sonarr is under high load
    # - the RAID array is being rebuilt
    # - etc.
    # TODO: Move to config
    SERVARR_HISTORY_WAIT = datetime.timedelta(seconds=120)
    # Map Servarr event types from the API to the Prunerr suffixes
    SERVARR_HISTORY_EVENT_TYPES = {
        "downloadFolderImported": "imported",
        "fileDeleted": "deleted",
        "downloadIgnored": "deleted",
    }

    # Prunerr constants
    PRUNERR_FILE_SUFFIXES = {".prunerr.json", "-servarr-imported.ln"}

    def __init__(self, config, servarrs, client, url, servarr_name=None, replay=False):
        """
        Do any config post-processing and set initial state.
        """
        # Download client handling
        self.client = client
        self.url = url
        session = self.client.get_session()

        # Prunerr config processing
        self.config = config

        # Download client config processing
        self.config["downloaders"]["min-download-free-space"] = (
            self.config["downloaders"]["max-download-bandwidth"]
            # Convert bandwidth bits to bytes
            / 8
        ) * (
            # Convert bandwidth MBps to Bps
            1024 * 1024
        ) * (
            # Multiply by seconds of download time margin
            self.config["downloaders"].get("min-download-time-margin", 3600)
        )
        # Set any download client config defaults for Prunerr
        session_download_path = pathlib.Path(session.download_dir)
        self.config["downloaders"]["download-dir"] = pathlib.Path(
            self.config["downloaders"].get("download-dir", session_download_path)
        )
        self.config["downloaders"]["imported-dir"] = pathlib.Path(
            self.config["downloaders"].get(
                "imported-dir", session_download_path.parent / "imported",
            )
        )
        self.config["downloaders"]["deleted-dir"] = pathlib.Path(
            self.config["downloaders"].get(
                "deleted-dir", session_download_path.parent / "deleted",
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
        self.servarrs = servarrs
        # Derive the destination directories for this download client for each type of
        # Servarr instance, e.g. `tvDirectory` vs `movieDirectory`.
        for servarr_config in self.servarrs.values():
            servarr_config["downloadDir"] = pathlib.Path(
                servarr_config["downloadclient"]["fieldValues"][
                    self.SERVARR_TYPE_MAPS[servarr_config["type"]]["download_dir_field"]
                ]
            ).resolve()
            if (
                    self.config["downloaders"]["download-dir"] not in
                    (servarr_config["downloadDir"] / "child").parents
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
                ]["client"](servarr_config["url"], servarr_config["api-key"],)

        # Should all events be handled again, even if previously processed.
        self.replay = replay

        # Initial state
        self.popen = self.copying = None
        self.corrupt = {}
        self.quiet = False

    def strip_type_prefix(
            self,
            servarr_type,
            prefixed,
            servarr_term="file_type",
    ):
        """
        Strip the particular Servarr type prefix if present.
        """
        # Map the different Servarr applications type terminology
        servarr_type_map = self.SERVARR_TYPE_MAPS[servarr_type]
        prefix = servarr_type_map[servarr_term]
        if prefixed.startswith(prefix):
            stripped = prefixed[len(prefix):]
            stripped = f"{stripped[0].lower()}{stripped[1:]}"
            # Don't strip the prefix for DB IDs in the Servarr API JSON, e.g.:
            # `movieId`.
            if stripped != "id":
                return stripped

        return prefixed

    def exec_(self):
        """
        Prune download client items once.
        """
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

        # Ensure that download client state matches Servarr state
        self.sync()

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
            "daemon-retry-codes", [10, 12, 20, 30, 35, 255],
        )
        to_copy = sorted(
            (
                torrent
                for torrent in self.torrents
                if torrent.status == "seeding"
                and not os.path.relpath(
                    torrent.downloadDir, self.config["downloaders"]["download-dir"],
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

    def update(self):
        self.torrents = [
            DownloadItem(self, torrent._client, torrent)
            for torrent in self.client.get_torrents()
        ]

    def list_torrent_files(self, torrent, download_dir=None):
        """
        Iterate over all torrent selected file paths that exist.
        """
        if download_dir is None:
            download_dir = torrent.downloadDir

        torrent_files = torrent.files()
        assert torrent_files, "Must be able to find torrent files"

        return (
            file_.name for file_ in torrent_files
            if file_.selected
            and os.path.exists(os.path.join(download_dir, file_.name))
        )

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
            while True:
                try:
                    # Don't loop until we successfully update everything
                    self.update()
                except (
                        socket.error,
                        error.TransmissionError,
                        arrapi.exceptions.ConnectionFailure) as exc:
                    logger.error(
                        "Connection error while updating from server: %s",
                        exc,
                    )
                    pass
                else:
                    time.sleep(1)
                    break

            start = time.time()
            try:
                self.exec_()
            except socket.error:
                logger.exception("Connection error while running daemon")
                pass
            # Don't repeat noisy messages from now on.
            self.quiet = True

            # Wait for the next interval
            poll = (
                self.config["daemon"].get("poll", 60,)
                if self.config["daemon"] else 60
            )
            # Loop early if the copy process finishes early
            while (
                self.popen is None or self.popen.poll() is None
            ) and time.time() - start < poll:
                time.sleep(1)

    def move_timeout(self, torrent, download_dir, move_timeout=5 * 60):
        """
        Block until a torrents files are no longer in the old location.

        Useful for both moving and deleting.
        """
        # Wait until the files are finished moving
        start = time.time()
        while list(self.list_torrent_files(torrent, download_dir)):
            if time.time() - start > move_timeout:
                raise TransmissionTimeout(
                    "Timed out waiting for {torrent} to move "
                    "from {download_dir!r}".format(**locals())
                )
            time.sleep(1)

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
            while (
                queue_page is None
                or (page_num * 250) <= queue_page["totalRecords"]
            ):
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
            download_item, operations_type="reviews",
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
                        download_item.hashString, delete_data=True,
                    )
                else:
                    delete_params = dict(removeFromClient="true")
                    if operation_config.get("blacklist", False):
                        delete_params["blacklist"] = "true"
                    queue_record["servarr_config"]["client"]._raw._delete(
                        f"queue/{queue_id}", **delete_params,
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
                    [download_item.hashString], **operation_config["change"],
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
                "Deleting from %s orphans to free space", len(orphans),
            )
            removed_torrents.extend(self.free_space_remove_torrents(orphans),)
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
            removed_torrents.extend(self.free_space_remove_torrents(deleted_torrents),)
            if self.free_space_maybe_resume():
                # There is now sufficient free disk space
                return removed_torrents

        # TODO: Maybe handle multiple downloading torrents for the
        # same Servarr item such as when trying several to see which
        # ones actually have decent download speeds?

        logger.error(
            "Running out of space but no items can be removed: %0.2f %s",
            *utils.format_size(session.download_dir_free_space),
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
            for torrent in self.torrents if torrent.status == "downloading"
        )
        if total_remaining_download > session.download_dir_free_space:
            logger.debug(
                "Total size of remaining downloads is greater than the available free "
                "space: %0.2f %s > %0.2f %s",
                *(
                    utils.format_size(total_remaining_download)
                    + utils.format_size(session.download_dir_free_space)
                ),
            )
        if (
                session.download_dir_free_space
                >= self.config["downloaders"]["min-download-free-space"]
        ):
            logger.debug(
                "Sufficient free space to continue downloading: %0.2f %s >= %0.2f %s",
                *(
                    utils.format_size(session.download_dir_free_space)
                    + utils.format_size(
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
                        utils.format_size(session.download_dir_free_space)
                        + utils.format_size(candidate.totalSize)
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
                        utils.format_size(session.download_dir_free_space)
                        + utils.format_size(metric)
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
                    or self.config["downloaders"]["imported-dir"] in
                    self.get_item_path(torrent).parents
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
                torrent_paths.add(os.path.join(
                    session.incomplete_dir,
                    self.get_item_root_name(torrent),
                ))
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
            du_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=0,
        )
        orphans = sorted(
            itertools.chain(
                *(
                    self._list_orphans(
                        session, torrent_dirs, torrent_paths, unstarted_names,
                        du, download_dir,
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
                    for orphan_size, orphan_path in orphans),
            )

        return orphans

    def _list_orphans(
            self, session, torrent_dirs, torrent_paths, unstarted_names,
            du, path,
    ):
        """Recursively list paths that aren't a part of any torrent."""
        path = pathlib.Path(path)
        for entry_path in pathlib.Path(path).iterdir():
            # Don't consider Prunerr files with any other corresponding
            # files present to be orphans.
            is_prunerr_file = False
            for prunerr_suffix in self.PRUNERR_FILE_SUFFIXES:
                if entry_path.name.endswith(prunerr_suffix):
                    entry_base = entry_path.name[:-len(prunerr_suffix)]
                    for unstarted_name in unstarted_names:
                        if unstarted_name.startswith(entry_base):
                            is_prunerr_file = True
                            break
                    entry_glob = f"{glob.escape(entry_base)}*"
                    non_orphans = {
                        match_path for match_path in itertools.chain(
                            pathlib.Path(session.incomplete_dir).glob(entry_glob),
                            entry_path.parent.glob(entry_glob)
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
                        session, torrent_dirs, torrent_paths, unstarted_names,
                        du, entry_path,
                ):
                    yield orphan

    def find_deleted(self):
        """
        Filter torrents that have been deleted from the Servarr library.
        """
        return self.sort_torrents_by_tracker(
            torrent for torrent in self.torrents
            # only those previously synced and moved
            if torrent.status == "seeding"
            and self.config["downloaders"]["deleted-dir"] in
            self.get_item_path(torrent).parents

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
                servarr_config, torrent=torrent,
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

    def match_item_indexer_urls(self, torrent):
        """
        Return the indexer name if the download item matches a configured tracker URL.
        """
        for possible_name, possible_urls in self.config.get(
                "indexers", {},
        ).get("urls", {}).items():
            for tracker in torrent.trackers:
                for action in ("announce", "scrape"):
                    tracker_url = tracker[action]
                    for indexer_url in possible_urls:
                        if tracker_url.startswith(indexer_url):
                            return possible_name
                            break

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
        cached_results[operations_type] = (include, (indexer_idx, ) + sort_key)
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
                    item_file for item_file in item_files
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
        if (
            session.speed_limit_down_enabled
            and (not speed_limit_down or speed_limit_down != session.speed_limit_down)
        ):
            if self.config["downloaders"].get(
                    "resume-set-download-bandwidth-limit", False,
            ) and speed_limit_down:
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
        assert (
            readded.download_dir == download_item.download_dir
        ), (
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

    def move_torrent(self, torrent, old_path, new_path):
        """
        Move the given torrent relative to its old path.
        """
        download_dir = torrent.downloadDir
        src_torrent_path = self.get_item_path(torrent)
        if pathlib.Path(old_path) not in src_torrent_path.parents:
            raise ValueError(
                f"Download item {torrent!r} not in expected location: "
                f"{str(old_path)!r} vs {download_dir!r}"
            )
        relative = os.path.relpath(download_dir, os.path.dirname(old_path))
        split = splitpath(relative)[1:]
        subpath = split and os.path.join(*split) or ""
        torrent_location = os.path.join(new_path, subpath)
        logger.info(
            "Moving %r: %r -> %r", torrent, torrent.download_dir, torrent_location
        )
        torrent.move_data(torrent_location)
        try:
            self.move_timeout(torrent, download_dir)
        except TransmissionTimeout as exc:
            logger.error("Moving torrent timed out, pausing: %s", exc)
            torrent.stop()
        finally:
            torrent.update()
        dst_torrent_path = self.get_item_path(torrent)

        # Move any non-torrent files managed by Prunerr
        # Explicit is better than implicit, specific e.g.: if a user has manually
        # extracted an archive in the old import location we want the orphan logic to
        # find it after Servarr has upgraded it
        if dst_torrent_path.is_file():
            import_links_pattern = str(src_torrent_path.with_name(
                f"{glob.escape(src_torrent_path.name)}**-servarr-imported.ln",
            ))
            data_path = src_torrent_path.with_suffix(".prunerr.json")
        else:
            import_links_pattern = str(src_torrent_path.with_name(
                f"{glob.escape(src_torrent_path.name)}**-servarr-imported.ln",
            ))
            data_path = src_torrent_path.with_name(
                f"{src_torrent_path.name}.prunerr.json"
            )
        prunerr_files = glob.glob(import_links_pattern, recursive=True)
        if data_path.exists():
            prunerr_files.append(data_path)
        for prunerr_file in prunerr_files:
            prunerr_file_path = pathlib.Path(prunerr_file)
            prunerr_file_relative = prunerr_file_path.relative_to(old_path)
            prunerr_file_dest = pathlib.Path(new_path) / prunerr_file_relative
            shutil.move(prunerr_file, prunerr_file_dest)
            if prunerr_file_path.parent != pathlib.Path(old_path) and not list(
                prunerr_file_path.parent.iterdir()
            ):
                prunerr_file_path.parent.rmdir()  # empty dir

        return torrent_location

    def get_dir_history(self, servarr_config, dir_id):
        """
        Retreive and collate the history for the given series/movie/etc..
        """
        dirs_history = servarr_config.setdefault("history", {}).setdefault("dirs", {})
        if dir_id in dirs_history:
            return dirs_history[dir_id]

        servarr_type_map = self.SERVARR_TYPE_MAPS[servarr_config["type"]]
        params = {f"{servarr_type_map['dir_type']}id": dir_id}
        logger.debug(
            "Requesting %r Servarr media directory history: %s",
            servarr_config["name"],
            json.dumps(params),
        )
        history_response = servarr_config["client"]._raw._get(
            f"history/{servarr_type_map['dir_type']}",
            **params,
        )
        dirs_history[dir_id] = self.collate_history_records(
            servarr_config, history_records=history_response,
        )
        return dirs_history[dir_id]

    def get_item_root_name(self, download_item):
        """
        Return the name of the first path element for all items in the download item.

        Needed because it's not always the same as the item's name.  If
        torrent has multiple files, assumes that all files are under the same top-level
        directory.
        """
        item_files = download_item.files()
        if item_files:
            return pathlib.Path(item_files[0].name).parts[0]
        else:
            return download_item.name

    def get_item_path(self, download_item):
        """
        Return the root path for all items in the download client item.

        Needed because it's not always the same as the item's download directory plus
        the item's name.
        """
        return (
            pathlib.Path(download_item.download_dir)
            / self.get_item_root_name(download_item)
        ).resolve()

    def sync(self):
        """
        Synchronize the state of download client items with Servarr event history.
        """
        # Ensure we have current history between subsequent `$ prunerr daemon` runs
        for servarr_config in self.servarrs.values():
            servarr_config["history"] = {}

        sync_results = []
        self.update()
        for torrent in self.torrents:
            download_path = self.get_item_path(torrent)

            # Determine if this download client item is in the download directory of a
            # Servarr instance.
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

                # This download client item is in the download directory of a Servarr
                # instance.  Sync the individual item.
                try:
                    item_result = self.sync_item(servarr_config, torrent)
                except Exception:
                    logger.exception(
                        "Un-handled exception syncing item: %r",
                        torrent,
                    )
                    if "DEBUG" in os.environ:
                        raise
                    else:
                        continue
                if item_result is not None:
                    sync_results.append(item_result)
                break

            else:
                if self.servarrs and not self.quiet:
                    logger.warning(
                        "Download item not managed by Servarr: %r",
                        torrent,
                    )

        return sync_results

    def sync_item(
            self,
            servarr_config,
            download_item,
            dir_id=None,
            servarr_history=None,
    ):
        """
        Ensure the download client state is in sync with Servarr state.
        """
        download_id = download_item.hashString.lower()
        download_path = self.get_item_path(download_item)
        download_data = download_item.prunerr_data
        for servarr_key in ("type", "name"):
            download_data.setdefault("servarr", {}).setdefault(
                servarr_key, servarr_config[servarr_key],
            )
        data_path = download_data["path"]

        servarr_type_map = self.SERVARR_TYPE_MAPS[servarr_config["type"]]
        dir_id_key = f"{servarr_type_map['dir_type']}Id"
        if not self.replay and dir_id is None and download_data.get("history"):
            # Try to correlate to the Servarr movie/series/etc. using existing Prunerr
            # data
            for history_record in reversed(download_data["history"].values()):
                if dir_id_key in history_record:
                    dir_id = history_record.get(dir_id_key)
                    break
        if dir_id is None:
            # Identify the item in the global Servarr history
            download_record = self.find_latest_item_history(
                servarr_config, download_item,
            )
            if download_record is None:
                logger.error(
                    "No %r Servarr history found, skipping: %r",
                    servarr_config["name"],
                    download_item,
                )
                return self.serialize_download_data(download_data, None, data_path)
            dir_id = download_record[dir_id_key]

        # Reconcile current Servarr history with the Prunerr data file
        existing_history = download_data["history"]
        download_history = download_data["history"] = {}
        if servarr_history is None:
            servarr_history = self.get_dir_history(servarr_config, dir_id)
        if download_id not in servarr_history["records"]["download_ids"]:
            logger.info(
                "Waiting for %r Servarr history for %r:  %r",
                servarr_config["name"],
                dir_id_key,
                download_item,
            )
            # Continue to below to write item Prunerr data
        seen_event_types = set()
        for history_record in reversed(
                servarr_history["records"]["download_ids"].get(download_id, []),
        ):
            # TODO: Skip duplicate events for multi-file items such as season packs

            # Preserve existing Prunerr data
            existing_record = existing_history.get(history_record["date"], {})
            history_record["prunerr"] = existing_record.get("prunerr", {})
            # Insert into the new history keyed by time stamp
            download_history[history_record["date"]] = history_record
            if "indexer" in history_record["data"]:
                # Cache indexer name for faster lookup
                download_data.setdefault("indexer", history_record["data"]["indexer"])

            # Synchronize the item's state with this history event/record
            if not self.replay and history_record["prunerr"].get("syncedDate"):
                if history_record["eventType"] not in seen_event_types:
                    seen_event_types.add(history_record["eventType"])
                    logger.debug(
                        "Previously synced %r event: %r",
                        history_record["eventType"],
                        download_item,
                    )
                continue
            # Run any handler for this specific event type, if defined
            handler_suffix = self.SERVARR_HISTORY_EVENT_TYPES.get(
                history_record["eventType"],
                history_record["eventType"],
            )
            handler_name = f"handle_{handler_suffix}"
            if hasattr(self, handler_name):
                handler = getattr(self, handler_name)
                logger.debug(
                    "Handling %r Servarr %r event: %r",
                    servarr_config["name"],
                    history_record["eventType"],
                    download_item,
                )
                handler_result = handler(
                    servarr_config,
                    download_item,
                    history_record,
                )
            else:
                logger.debug(
                    "No handler found for Servarr %r event type: %s",
                    servarr_config["name"],
                    history_record["eventType"],
                )
                # Default handler actions
                # Ensure the download item's location matches the Servarr state
                handler_result = self.sync_item_location(
                    servarr_config,
                    download_item,
                    history_record,
                )
            if handler_result is not None:
                history_record["prunerr"]["handlerResult"] = str(handler_result)
                history_record["prunerr"]["syncedDate"] = datetime.datetime.now()

        # If no indexer was found in the Servarr history,
        # try to match by the tracker URLs
        if "indexer" not in download_data:
            download_data["indexer"] = self.match_item_indexer_urls(download_item)

        # Update Prunerr JSON data file, after the handler has run to allow it to update
        # history record prunerr data.
        self.serialize_download_data(download_data, download_history, data_path)

        dst_download_path = self.get_item_path(download_item)
        if dst_download_path != download_path:
            return str(dst_download_path)

    def sync_item_location(self, servarr_config, download_item, history_record):
        """
        Ensure the download item location matches its Servarr state.
        """
        download_path = self.get_item_path(download_item)
        event_locations = self.SERVARR_EVENT_LOCATIONS[history_record["eventType"]]

        src_path = servarr_config[event_locations["src"]]
        dst_path = servarr_config[event_locations["dst"]]
        if dst_path in download_path.parents:
            logger.debug(
                "Download item %r already in correct location: %r",
                download_item,
                str(download_path),
            )
            return str(download_path)

        if src_path not in download_path.parents:
            event_paths = set()
            for other_event_locations in self.SERVARR_EVENT_LOCATIONS.values():
                event_paths.update(other_event_locations.values())
            for event_path in event_paths:
                if servarr_config[event_path] in download_path.parents:
                    logger.warning(
                        "Download item %r not in correct managed dir, %r: %r",
                        download_item,
                        str(src_path),
                        str(download_path),
                    )
                    src_path = servarr_config[event_path]
                    break
            else:
                logger.error(
                    "Download item %r not in a managed dir: %r",
                    download_item,
                    str(download_path),
                )
                return str(download_path)

        download_item.update()
        if not download_item.files():
            logger.warning(
                "Download item has no files yet: %r",
                download_item,
            )
            return

        return self.move_torrent(download_item, src_path, dst_path)

    def handle_imported(
            self,
            servarr_config,
            download_item,
            history_record,
    ):
        """
        Handle Servarr imported event, wait for import to complete, then move.
        """
        download_data = download_item.prunerr_data
        if "latestImportedDate" not in download_data:
            download_data["latestImportedDate"] = history_record["date"]
        wait_duration = datetime.datetime.now(
            download_data["latestImportedDate"].tzinfo
        ) - download_data["latestImportedDate"]
        if wait_duration < self.SERVARR_HISTORY_WAIT:
            logger.info(
                "Waiting for import to complete before moving, %s so far: %r",
                wait_duration,
                download_item,
            )
            return
        elif not self.replay:
            imported_records = [
                imported_record for imported_record in download_data["history"].values()
                if imported_record["eventType"] == "downloadFolderImported"
            ]
            if imported_records:
                logger_level = logger.debug
            else:
                logger_level = logger.error
            logger_level(
                "Found %s imported history records after %s for %r",
                len(imported_records),
                wait_duration,
                download_item,
            )

        # TODO: If none of the imported files are among the torrent's files, such as
        # when the torrent contains archives which have been extracted and imported,
        # move the item to the deleted folder.
        # https://github.com/davidnewhall/unpackerr

        # If we're not waiting for history, then proceed to move the download item.
        # Ensure the download item's location matches the Servarr state.
        history_record["prunerr"]["handlerResult"] = str(self.sync_item_location(
            servarr_config,
            download_item,
            history_record,
        ))
        download_item.update()

        # Reflect imported files in the download client item using symbolic links
        old_dropped_path = pathlib.Path(history_record["data"]["droppedPath"])
        if servarr_config["downloadDir"] not in old_dropped_path.parents:
            logger.warning(
                "Servarr dropped path %r not in download client's download directory %r"
                "for %r",
                history_record["data"]["droppedPath"],
                servarr_config["downloadDir"],
                download_item,
            )
            return download_item
        relative_to_download_dir = old_dropped_path.relative_to(
            servarr_config["downloadDir"],
        )
        new_dropped_path = download_item.downloadDir / relative_to_download_dir
        link_path = (
            new_dropped_path.parent / f"{new_dropped_path.stem}-servarr-imported.ln"
        )
        imported_link_target = pathlib.Path(
            os.path.relpath(history_record["data"]["importedPath"], link_path.parent)
        )
        if os.path.lexists(link_path):
            if not link_path.is_symlink():
                logger.error(
                    "Imported file link is not a symlink: %s", link_path,
                )
            elif pathlib.Path(os.readlink(link_path)) != imported_link_target:
                logger.error(
                    "Download file symlink to wrong imported file: %s -> %s",
                    link_path,
                    imported_link_target,
                )
        elif not link_path.parent.exists():
            logger.error(
                "Imported file link directory no longer exists: %s", link_path,
            )
        else:
            logger.info(
                "Symlinking imported file: %s -> %s", link_path, imported_link_target,
            )
            if not (link_path.parent / imported_link_target).is_file():
                logger.error(
                    "Symlink download file to imported file that doesn't exist: "
                    "%s -> %s",
                    link_path,
                    imported_link_target,
                )
            link_path.symlink_to(imported_link_target)

        return download_item

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
            return DownloadItem(self, torrent._client, torrent)
        except KeyError:
            # Can happen if the download client item has been manually deleted
            logger.error(
                "Could not find item in download client "
                "for Servarr imported event: %s",
                download_id,
            )

    def find_latest_item_history(self, servarr_config, torrent):
        """
        Find the most recent Servarr history record for the given torrent if any.

        Cache these lookups as we page through the history across subsequent calls.
        """
        servarr_history = servarr_config.setdefault("history", {})
        servarr_history.setdefault("page", 1)
        download_id = torrent.hashString.lower()

        # Page through history until a Servarr import event is found for this download
        # item.
        history_page = None
        download_record = indexer_record = None
        while (
            # Is history for this Servarr instance exhausted?
            history_page is None
            or (servarr_history["page"] * 250) <= history_page["totalRecords"]
        ) and indexer_record is None:
            logger.debug(
                "Requesting %r Servarr history page: %s",
                servarr_config["name"],
                servarr_history["page"],
            )
            history_page = servarr_config["client"]._raw._get(
                "history",
                # Maximum Servarr page size
                pageSize=250,
                page=servarr_history["page"],
            )
            collated_history = self.collate_history_records(
                servarr_config,
                history_records=history_page["records"],
                servarr_history=servarr_history,
            )
            for history_record in collated_history["records"]["download_ids"].get(
                    download_id, [],
            ):
                if "downloadId" in history_record:
                    if download_record is None:
                        # Sufficient to identify download client item, fallback
                        download_record = history_record
                    if "indexer" in history_record["data"]:
                        # Can also identify the indexer, optimal
                        indexer_record = history_record
                        break
            servarr_history["page"] += 1

        return indexer_record if indexer_record is not None else download_record

    def deserialize_history(self, history_record):
        """
        Convert Servarr history values to native Python types when possible.
        """
        for history_data in (
                history_record,
                history_record["data"],
                history_record.get("prunerr", {}),
        ):
            for key, value in list(history_data.items()):
                # Perform any data transformations, e.g. to native Python types
                if key == "date" or key.endswith("Date"):
                    # More efficient than dateutil.parser.parse(value)
                    history_data[key] = ciso8601.parse_datetime(value)
        return history_record

    def serialize_history(self, history_record):
        """
        Convert Servarr history values to native Python types when possible.
        """
        # Prevent serialized values from leaking into cached Servarr history
        for history_data in (
                history_record,
                history_record["data"],
                history_record.get("prunerr", {}),
        ):
            for key, value in list(history_data.items()):
                # Perform any data transformations, e.g. to native Python types
                if key == "date" or key.endswith("Date"):
                    history_data[key] = value.strftime(self.SERVARR_DATETIME_FORMAT)
        return history_record

    def serialize_download_data(self, download_data, download_history, data_path):
        """
        Serialize an item's Prunerr data and write to the Prunerr data file.
        """
        download_data = copy.deepcopy(download_data)
        # Convert loaded JSON to native types where possible
        if download_history is not None:
            download_history = {
                history_date.strftime(self.SERVARR_DATETIME_FORMAT):
                self.serialize_history(copy.deepcopy(history_record))
                for history_date, history_record in
                download_history.items()
            }
        download_data["history"] = download_history
        if "latestImportedDate" in download_data:
            download_data["latestImportedDate"] = download_data[
                "latestImportedDate"
            ].strftime(self.SERVARR_DATETIME_FORMAT)
        if "path" in download_data:
            download_data["path"] = str(download_data["path"])
        existing_deserialized = ""
        if data_path.exists():
            with data_path.open("r") as data_read:
                existing_deserialized = data_read.read()
        with data_path.open("w") as data_opened:
            logger.debug("Writing Prunerr download item data: %s", data_path)
            try:
                return json.dump(download_data, data_opened, indent=2)
            except Exception:
                logger.exception(
                    "Failed to serialize to JSON file, %r:\n%s",
                    str(data_path),
                    pprint.pformat(download_data),
                )
                data_opened.seek(0)
                data_opened.write(existing_deserialized)

    def collate_history_records(
            self, servarr_config, history_records, servarr_history=None,
    ):
        """
        Collate Servarr history response under best ids for each history record.
        """
        if servarr_history is None:
            # Start fresh by default
            servarr_history = {}
        servarr_history.setdefault(
            "records", dict(download_ids={}, source_titles={}))
        servarr_history.setdefault(
            "event_types", dict(download_ids={}, source_titles={}))

        for history_record in history_records:
            self.deserialize_history(history_record)
            for history_data in (history_record, history_record["data"]):
                for key, value in list(history_data.items()):
                    # Normalize specific values using Servarr type-specific prefixes
                    if key == "eventType":
                        history_data[key] = self.strip_type_prefix(
                            servarr_config["type"],
                            value,
                        )
                    # Normalize keys using prefixes specific to the Servarr type
                    key_stripped = self.strip_type_prefix(servarr_config["type"], key)
                    history_data[key_stripped] = history_data.pop(key)

            # Collate history under the best available identifier that may be
            # matched to download client items
            if "downloadId" in history_record:
                # History record can be matched exactly to the download client item
                servarr_history["records"]["download_ids"].setdefault(
                    history_record["downloadId"].lower(), [],
                ).append(history_record)
                servarr_history["event_types"]["download_ids"].setdefault(
                    history_record["downloadId"].lower(), {},
                ).setdefault(history_record["eventType"], []).append(history_record)
            if "importedPath" in history_record["data"]:
                # Capture a reference that may match to more recent history record
                # below, such as deleting upon upgrade
                servarr_history["records"]["source_titles"].setdefault(
                    history_record["data"]["importedPath"], [],
                ).append(history_record)
                servarr_history["event_types"]["source_titles"].setdefault(
                    history_record["data"]["importedPath"], {},
                ).setdefault(history_record["eventType"], []).append(history_record)
            if "sourceTitle" in history_record:
                # Can't match exactly to a download client item, capture a reference
                # that may match to more recent history record below, such as
                # deleting upon upgrade
                servarr_history["records"]["source_titles"].setdefault(
                    history_record["sourceTitle"], [],
                ).append(history_record)
                servarr_history["event_types"]["source_titles"].setdefault(
                    history_record["sourceTitle"], {},
                ).setdefault(history_record["eventType"], []).append(history_record)

            # Match this older import history record to previously processed, newer,
            # records that don't match exactly to a download client item, such as
            # deleting upon upgrade
            if (
                "downloadId" in history_record
                and "importedPath" in history_record["data"]
                and history_record["data"]["importedPath"]
                in servarr_history["records"]["source_titles"]
            ):
                # Insert previous, newer history records under the download id that
                # matches the import path for this older record
                source_titles = servarr_history["records"]["source_titles"][
                    history_record["data"]["importedPath"]
                ]
                download_records = servarr_history["records"]["download_ids"][
                    history_record["downloadId"].lower()
                ]
                latest_download_record = download_records[0]
                newer_records = list(
                    itertools.takewhile(
                        lambda later_record: later_record["date"]
                        > latest_download_record["date"],
                        source_titles,
                    )
                )
                download_records[:0] = newer_records
                # Do the same for each even type
                newer_event_types = {}
                for newer_record in newer_records:
                    newer_event_types.setdefault(
                        newer_record["eventType"], [],
                    ).append(newer_record)
                for (event_type, newer_event_records,) in newer_event_types.items():
                    servarr_history["event_types"]["download_ids"][
                        history_record["downloadId"].lower()
                    ].setdefault(event_type, [])[:0] = newer_event_records

                # Also include history records under the imported path
                servarr_history["records"]["source_titles"].setdefault(
                    history_record["data"]["importedPath"], [],
                ).append(history_record)
                servarr_history["event_types"]["source_titles"].setdefault(
                    history_record["data"]["importedPath"], {},
                ).setdefault(history_record["eventType"], []).append(history_record)

        return servarr_history

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
                            not download_path.exists() or (
                                incomplete_path not in orphan_path.parents
                                and client_download_path not in orphan_path.parents
                            )
                    ):
                        logger.info(
                            "Restoring data: %r -> %r",
                            str(download_path), str(orphan_path),
                        )
                        download_item.locate_data(str(orphan_path.parent))
                        # Collect results of actions taken
                        restored_items.setdefault(download_item.name, {}).setdefault(
                            "orphans",
                            [],
                        ).append(str(orphan_path))

                    # Found the largest matching path, no need to continue
                    break

            # Next try to restore as much as possible from the Servarr history
            for servarr_config in self.servarrs.values():
                servarr_history = servarr_config.setdefault("history", {})
                self.find_latest_item_history(
                    servarr_config, torrent=download_item,
                )
                item_history = servarr_history["records"]["download_ids"].get(
                    download_id, [],
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
                        str(download_path), str(dst_path),
                    )
                    new_download_path = self.move_torrent(
                        download_item, download_path.parent, dst_path,
                    )
                    # Collect results of actions taken
                    restored_items.setdefault(download_item.name, {}).setdefault(
                        "paths",
                        [],
                    ).append(str(new_download_path))

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
                            relative_path = pathlib.Path(*dropped_path.parts[
                                dropped_path.parts.index(item_root_name):
                            ])
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
                                    parents=True, exist_ok=True,
                                )
                            logger.info(
                                "Restoring imported path: %r -> %r",
                                str(imported_path), str(current_dropped_path),
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
            item_files_exist = [
                item_file for item_file in download_item.files()
                if (incomplete_path / item_file.name).exists
                or (download_parent / item_file.name).exists
            ]
            if (
                    (download_item.status == 'stopped' and item_files_exist)
                    or restored_items.get(download_item.name, {}).get("orphans", [])
                    or restored_items.get(download_item.name, {}).get("imported", [])
            ):
                logger.info(
                    "Verifying and resuming: %r", download_item,
                )
                self.client.verify_torrent([download_item.hashString])
                download_item.start()

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


def collect_downloaders(config):
    """
    Aggregate all download clients from all Servarr instances defined in the config.
    """
    # TODO: Cleanup with re-use in mind.  Specifically how to connect the API clients
    # for Servarr and download client with their configs, both Prunerr config and
    # settings from Servarr.

    # Collect connections information for all unique download clients
    downloader_urls = {}
    for servarr_config in config.get("servarrs", []):
        servarr_config["client"] = servarr_client = Prunerr.SERVARR_TYPE_MAPS[
            servarr_config["type"]
        ]["client"](servarr_config["url"], servarr_config["api-key"],)

        logger.debug(
            "Requesting %r Servarr download clients settings",
            servarr_config["name"],
        )
        for downloader_config in servarr_client._raw._get("downloadclient"):
            if not downloader_config["enable"]:
                continue

            # Create a copy specific to this download client so we can modify freely
            servarr_config = dict(servarr_config)
            servarr_config["downloadclient"] = downloader_config

            downloader_config["fieldValues"] = field_values = {
                downloader_config_field["name"]: downloader_config_field["value"]
                for downloader_config_field in downloader_config["fields"]
                if "value" in downloader_config_field
            }
            downloader_url = urllib.parse.SplitResult(
                "http" if not field_values["useSsl"] else "https",
                f"{field_values['username']}:{field_values['password']}@"
                f"{field_values['host']}:{field_values['port']}",
                field_values["urlBase"],
                None,
                None,
            )
            # Use the same config dict when a download client is used in multiple
            # Servarr instances
            downloader_config = downloader_urls.setdefault(
                downloader_url, downloader_config,
            )
            downloader_config.setdefault("servarrs", {})[
                servarr_config["name"]
            ] = servarr_config

    # Include any download clients not connected to a Servarr instance
    for downloader_url_str in config.get("downloaders", {}).get("urls", []):
        downloader_url = urllib.parse.urlsplit(downloader_url_str)
        downloader_urls.setdefault(downloader_url, {})

    # Connect clients to all download clients
    downloaders = {}
    for download_url, downloader_config in downloader_urls.items():
        # Aggregate the download clients from all Servarrs so that we run for each
        # download client once even when used for multiple Servarr instances
        if downloader_url.geturl() not in downloaders:
            downloader_config["client"] = transmission_rpc.client.Client(
                protocol=downloader_url.scheme,
                host=downloader_url.hostname,
                port=downloader_url.port,
                path=downloader_url.path,
                username=downloader_url.username,
                password=downloader_url.password,
            )
            downloaders[downloader_url.geturl()] = downloader_config

    return downloaders


def sync(prunerr):
    prunerr.update()
    return len(prunerr.sync())


sync.__doc__ = Prunerr.sync.__doc__
parser_sync = subparsers.add_parser("sync", help=sync.__doc__.strip())
parser_sync.set_defaults(command=sync)


def exec_(prunerr):
    prunerr.update()
    result = prunerr.exec_()
    if prunerr.popen is not None:
        logger.info("Letting running copy finish: %s", prunerr.copying)
        prunerr.popen.wait()
    return result


exec_.__doc__ = Prunerr.exec_.__doc__
parser_exec = subparsers.add_parser("exec", help=exec_.__doc__.strip())
parser_exec.set_defaults(command=exec_)


def daemon(prunerr):
    return prunerr.daemon()


daemon.__doc__ = Prunerr.daemon.__doc__
parser_daemon = subparsers.add_parser("daemon", help=daemon.__doc__.strip())
parser_daemon.set_defaults(command=daemon)


def sync(prunerr):
    prunerr.update()
    return prunerr.sync()


sync.__doc__ = Prunerr.sync.__doc__
parser_sync = subparsers.add_parser("sync", help=sync.__doc__.strip())
parser_sync.add_argument(
    "--replay",
    "-r",
    action="store_true",
    help="""\
Also run operations for Servarr events/history that have previously been run.
""",
)
parser_sync.set_defaults(command=sync)


def restore_data(prunerr):
    prunerr.update()
    return prunerr.restore_data()


restore_data.__doc__ = Prunerr.restore_data.__doc__
parser_restore_data = subparsers.add_parser(
    "restore-data", help=restore_data.__doc__.strip(),
)
parser_restore_data.set_defaults(command=restore_data)


def main(args=None):
    logging.basicConfig(level=logging.INFO)
    # Want just our logger, not transmission-rpc's to log DEBUG
    if "DEBUG" in os.environ:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logger.setLevel(level)
    # Avoid logging all JSON responses, particularly the very large history responses
    # from Servarr APIs
    logging.getLogger("arrapi.api").setLevel(logging.INFO)

    parsed_args = parser.parse_args(args)
    shared_kwargs = dict(vars(parsed_args))
    del shared_kwargs["command"]

    # Iterate over each of the unique enabled download clients in each Servarr instances
    # and run the sub-command for each of those.
    downloaders = collect_downloaders(shared_kwargs["config"])
    for downloader_url, downloader_config in downloaders.items():
        prunerr_kwargs = dict(shared_kwargs)
        prunerr_kwargs["servarrs"] = downloader_config.get("servarrs", {})
        prunerr_kwargs["client"] = downloader_config["client"]
        prunerr_kwargs["url"] = downloader_url
        prunerr = Prunerr(**prunerr_kwargs)
        results = parsed_args.command(prunerr)
        if results:
            if isinstance(results, list):
                results = len(results)
            logger.info(
                "%r results for download client %r:\n%s",
                parsed_args.command.__name__,
                downloader_url,
                pprint.pformat(results, width=100),
            )


main.__doc__ = __doc__


if __name__ == "__main__":
    main()
