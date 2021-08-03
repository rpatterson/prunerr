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

import ciso8601
import yaml

import arrapi

import transmission_rpc
from transmission_rpc import utils
from transmission_rpc import error

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
    # Map Servarr event types from Custom Script environment variables to the Prunerr
    # suffixes
    SERVARR_CUSTOM_SCRIPT_EVENT_TYPES = {
        "Grab": "grabbed",
        "Download": "imported",
        "Download": "imported",
        "Rename": "renamed",
        "Deleted": "deleted",
        "FileDelete": "deleted",
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
        self.config["downloaders"]["download-dir"] = self.config["downloaders"].get(
            "download-dir",
            os.path.join(os.path.dirname(session.download_dir), "downloads"),
        )
        self.config["downloaders"]["imported-dir"] = self.config["downloaders"].get(
            "imported-dir",
            os.path.join(os.path.dirname(session.download_dir), "imported"),
        )
        self.config["downloaders"]["deleted-dir"] = self.config["downloaders"].get(
            "deleted-dir",
            os.path.join(os.path.dirname(session.download_dir), "deleted"),
        )

        # Indexers config processing
        self.indexer_configs = {
            indexer_config["name"]: indexer_config
            for indexer_config in
            config.get("indexers", {}).get("priorities", [])
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
            servarr_config["importedDir"] = (
                pathlib.Path(self.config["downloaders"]["imported-dir"])
                / (
                    servarr_config["downloadDir"].relative_to(
                        self.config["downloaders"]["download-dir"]
                    )
                )
            ).resolve()
            servarr_config["deletedDir"] = (
                pathlib.Path(self.config["downloaders"]["deleted-dir"])
                / (
                    servarr_config["downloadDir"].relative_to(
                        self.config["downloaders"]["download-dir"]
                    )
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
            # Don't strip the names of custom script environment variables that are
            # actually type-specific, e.g.: `sonarr_series_tvdbid`.  Neither strip the
            # prefix for DB IDs in the Servarr API JSON, e.g.: `movieId`.
            if not stripped.startswith("_") and stripped != "id":
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
        self.corrupt.update(self.verify_corrupted())
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

        if self.config["downloaders"].get("copy"):
            # Launch copy of most optimal, fully downloaded torrent in the downloads
            # dir.
            self._exec_copy(session)

        # Ensure that download client state matches Servarr state
        self.sync()

        # Free disk space if needed
        self.free_space()

    def _exec_copy(self, session):
        """
        Launch copy of most optimal, fully downloaded torrent in the downloads dir.
        """
        destination = self.config["downloaders"]["copy"]["destination"]
        command = self.config["downloaders"]["copy"]["command"]
        imported_dir = self.config["downloaders"].get(
            "imported-dir",
            os.path.join(os.path.dirname(session.download_dir), "imported"),
        )
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
                if not to_copy or self.copying.id == to_copy[0].id:
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
                if to_copy and self.copying.id == to_copy[0].id:
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
        self.torrents = self.client.get_torrents()

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
        while True:
            while True:
                try:
                    # Don't loop until we successfully update everything
                    self.update()
                except (
                        socket.error,
                        error.TransmissionError,
                        arrapi.exceptions.ConnectionFailure):
                    logger.exception("Connection error while updating from server")
                    pass
                else:
                    break

            start = time.time()
            try:
                self.exec_()
            except socket.error:
                logger.exception("Connection error while running daemon")
                pass

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
            key=lambda item: self.exec_indexer_priorities(item[1])[1],
            reverse=True,
        )

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
                candidate = self.client.get_torrent(int)

            # Handle actual torrents recognized by the download client
            if isinstance(candidate, transmission_rpc.Torrent):
                self.exec_indexer_priorities(candidate)
                logger.info(
                    "Deleting seeding %s to free space, "
                    "%0.2f %s + %0.2f %s: indexer=%s, priority=%s, ratio=%0.2f",
                    candidate,
                    *(
                        utils.format_size(session.download_dir_free_space)
                        + utils.format_size(candidate.totalSize)
                        + (
                            candidate.prunerr_indexer_name,
                            candidate.bandwidthPriority,
                            candidate.ratio,
                        )
                    ),
                )
                download_dir = candidate.downloadDir
                self.client.remove_torrent(candidate.id, delete_data=True)
                self.move_timeout(candidate, download_dir)

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
        session = self.client.get_session()
        return self.sort_torrents_by_tracker(
            torrent
            for torrent in self.torrents
            if (
                (
                    torrent.status == "downloading"
                    or torrent.downloadDir.startswith(
                        self.config["downloaders"].get(
                            "imported-dir",
                            os.path.join(
                                os.path.dirname(session.download_dir), "imported"
                            ),
                        )
                    )
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
        session = self.client.get_session()
        download_dirs = (
            # Transmission's `incomplete` directory for incomplete, leeching torrents
            session.incomplete_dir,
            # Transmission's `downloads` directory for complete, seeding torrents
            session.download_dir,
            # The Prunerr directories that reflect the state of download items in
            # Servarr.
            self.config["downloaders"].get(
                "imported-dir",
                os.path.join(os.path.dirname(session.download_dir), "imported"),
            ),
            self.config["downloaders"].get(
                "deleted-dir",
                os.path.join(os.path.dirname(session.download_dir), "deleted"),
            ),
        )

        # Assemble all directories whose descendants are torrents
        torrent_dirs = set()
        torrent_paths = set()
        for torrent in self.torrents:
            # Transmission's `incomplete` directory for incomplete, leeching torrents
            torrent_paths.add(os.path.join(session.incomplete_dir, torrent.name))
            # Transmission's `downloads` directory for complete, seeding torrents
            torrent_dir, tail = os.path.split(torrent.downloadDir + os.sep)
            # Include the ancestors of the torrent's path
            # so we know what dirs to descend into when looking for orphans
            while torrent_dir not in torrent_dirs or torrent_dir != os.sep:
                torrent_dirs.add(torrent_dir)
                torrent_dir, tail = os.path.split(torrent_dir)
            torrent_paths.add(os.path.join(torrent.downloadDir, torrent.name))

        # Sort the orphans by total directory size
        # TODO Windows compatibility
        du_cmd = ["du", "-s", "--block-size=1", "--files0-from=-"]
        du = subprocess.Popen(
            du_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=0,
        )
        orphans = sorted(
            itertools.chain(
                *(
                    self._list_orphans(torrent_dirs, torrent_paths, du, download_dir)
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

    def _list_orphans(self, torrent_dirs, torrent_paths, du, path):
        """Recursively list paths that aren't a part of any torrent."""
        path = pathlib.Path(path)
        for entry_path in pathlib.Path(path).iterdir():
            # Don't consider Prunerr files with any other corresponding
            # files present to be orphans.
            non_orphans = None
            for prunerr_suffix in self.PRUNERR_FILE_SUFFIXES:
                if entry_path.name.endswith(prunerr_suffix):
                    entry_base = entry_path.name[:-len(prunerr_suffix)]
                    non_orphans = {
                        match_path for match_path in entry_path.parent.glob(
                            f"{glob.escape(entry_base)}*"
                        )
                        if not {
                                match_path
                                for prunerr_suffix in self.PRUNERR_FILE_SUFFIXES
                                if match_path.name.endswith(prunerr_suffix)
                        }
                    }
                    if non_orphans:
                        break
            if non_orphans:
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
                    torrent_dirs, torrent_paths, du, entry_path
                ):
                    yield orphan

    def find_deleted(self):
        """
        Filter torrents that have been deleted from the Servarr library.
        """
        session = self.client.get_session()
        return self.sort_torrents_by_tracker(
            torrent for torrent in self.torrents
            # only those previously synced and moved
            if torrent.status == "seeding"
            and torrent.downloadDir.startswith(
                self.config["downloaders"].get(
                    "deleted-dir",
                    os.path.join(os.path.dirname(session.download_dir), "deleted"),
                )
            )
            # TODO: Optionally include imported items for Servarr configurations that
            # copy items instead of making hard-links, such as when the download client
            # isn't on the same host as the Servarr instance
            and self.exec_indexer_priorities(torrent)[0]
        )

    def exec_indexer_priorities(self, torrent):
        """
        Lookup the indexer for this torrent and calculate it's priority.
        """
        if hasattr(torrent, "prunerr_indexer_sort_key"):
            return torrent.prunerr_indexer_include, torrent.prunerr_indexer_sort_key

        indexer_name = None
        # Try to find an indexer name from the items Servarr history
        for servarr_config in self.servarrs.values():
            torrent_history = self.find_item_history(servarr_config, torrent=torrent)
            if torrent_history:
                for history_record in torrent_history:
                    if "indexer" in history_record["data"]:
                        indexer_name = history_record["data"]["indexer"]
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
            if indexer_name is not None:
                break

        # Lookup the indexer priority configuration
        if not indexer_name:
            # Match by indexer URLs when no indexer name is available
            for possible_name, possible_config in self.indexer_configs.items():
                if "urls" not in possible_config:
                    continue
                for tracker in torrent.trackers:
                    for action in ("announce", "scrape"):
                        tracker_url = tracker[action]
                        for indexer_url in possible_config["urls"]:
                            if tracker_url.startswith(indexer_url):
                                indexer_name = possible_name
                                break
                        if indexer_name:
                            break
                    if indexer_name:
                        break
                if indexer_name:
                    break
        torrent.prunerr_indexer_name = indexer_name
        if indexer_name not in self.indexer_configs:
            indexer_name = None
        indexer_idx = list(self.indexer_configs.keys()).index(indexer_name)
        indexer_config = self.indexer_configs[indexer_name]

        include, sort_key = self.exec_operations(indexer_config["operations"], torrent)
        torrent.prunerr_indexer_include = include
        torrent.prunerr_indexer_sort_key = (indexer_idx, ) + sort_key
        return torrent.prunerr_indexer_include, torrent.prunerr_indexer_sort_key

    def exec_operations(self, operation_configs, torrent):
        """
        Execute each of the configured indexer priority operations
        """
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
            # Apply any restrictions that can apply across different operation types
            sort_bool = None
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
        if hasattr(torrent, operation_config["name"]):
            return getattr(torrent, operation_config["name"])
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
            (torrent.id, torrent)
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
        torrents_were_readded = False
        for torrent in self.torrents:
            if not (
                torrent.status == "stopped"
                and torrent.error == 3
                and torrent.errorString.lower().startswith("no data found")
            ):
                continue
            torrent = self.client.get_torrent(torrent.id)
            logger.error("No data found for %s, re-adding", torrent)
            with open(torrent.torrentFile, mode="r+b") as torrent_opened:
                self.client.remove_torrent(ids=[torrent.id])
                self.client.add_torrent(
                    torrent=torrent_opened,
                    # These are the only fields from the `add_torrent()` call signature
                    # in the docs I could see corresponding fields for in the
                    # representation of a torrent.
                    bandwidthPriority=torrent.bandwidthPriority,
                    download_dir=torrent.download_dir,
                    peer_limit=torrent.peer_limit,
                )
            torrents_were_readded = True
        if torrents_were_readded:
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
        history_response = servarr_config["client"]._get(
            f"history/{servarr_type_map['dir_type']}",
            **params,
        )
        # Avoid `pprint` overhead if we're not logging the message
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Received Sonarr history API response for %r:\n%s",
                dir_id,
                pprint.pformat(history_response),
            )
        dirs_history[dir_id] = self.collate_history_records(
            servarr_config, history_records=history_response,
        )
        return dirs_history[dir_id]

    def get_item_path(self, download_item):
        """
        Return the root path for all items in the download client item.

        Needed because it's not always the same as the item's download directory plus
        the item's name.
        """
        item_files = download_item.files()
        if item_files:
            item_root_name = pathlib.Path(item_files[0].name).parts[0]
        else:
            item_root_name = download_item.name
        return (pathlib.Path(download_item.download_dir) / item_root_name).resolve()

    def sync(self):
        """
        Synchronize the state of download client items with Servarr event history.

        Match the state of each current download client item as if they had been
        processed through the `handle` sub-command as a Servarr `Custom Script`.
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
                item_result = self.sync_item(servarr_config, torrent, is_realtime=False)
                if item_result is not None:
                    sync_results.append(item_result)

        return sync_results

    def dispatch_event(self, servarr_config, **custom_script_kwargs):
        """
        Handle a Servarr event after custom script env vars transformed to kwargs.
        """
        servarr_type_map = self.SERVARR_TYPE_MAPS[self.servarr_config["type"]]
        if custom_script_kwargs["eventtype"].lower() == "test":
            return self.handle_test(servarr_config, **custom_script_kwargs)
        elif custom_script_kwargs["eventtype"].lower() == "HealthIssue":
            return
        dir_id_key = f"{servarr_type_map['dir_type']}_id"
        if dir_id_key not in custom_script_kwargs:
            raise ServarrEventError(
                f"No {servarr_config['name']!r} Sonarr {dir_id_key!r} DB id "
                f"passed to {custom_script_kwargs['eventtype']!r} event handler",
            )
        dir_id = custom_script_kwargs[dir_id_key]
        download_id = custom_script_kwargs.get("download_id")
        servarr_history = None
        if not download_id:
            servarr_history = self.get_dir_history(self.servarr_config, dir_id)
            download_id = self.select_imported_download_id(
                servarr_history, custom_script_kwargs["file_path"],
            )
        if not download_id:
            logger.warning(
                "Could not match %r Servarr %r event to a download client item",
                servarr_config["name"],
                custom_script_kwargs["eventtype"],
            )
            return
        download_item = self.get_download_item(download_id)
        return self.sync_item(
                self.servarr_config,
                download_item,
                dir_id=dir_id,
                servarr_history=servarr_history,
            )

    def sync_item(
            self,
            servarr_config,
            download_item,
            dir_id=None,
            servarr_history=None,
            is_realtime=True,
    ):
        """
        Ensure the download client state is in sync with Servarr state.
        """
        download_id = download_item.hashString.lower()
        download_path = self.get_item_path(download_item)

        # Load the Prunerr data file
        download_data = dict(history={})
        if download_path.is_file():
            data_path = download_path.with_suffix(".prunerr.json")
        else:
            data_path = download_path.with_name(f"{download_path.name}.prunerr.json")
        if not self.replay and data_path.exists() and data_path.stat().st_size:
            with data_path.open() as data_opened:
                try:
                    download_data = json.load(data_opened)
                except Exception:
                    logger.exception("Failed to deserialize JSON file: %s", data_path)
            if download_data["history"] is None:
                logger.warning(
                    "No history previously found for %r Servarr download item, "
                    "skipping: %r",
                    servarr_config["name"],
                    download_item,
                )
                return
            # Convert loaded JSON to native types where possible
            download_data["history"] = {
                ciso8601.parse_datetime(history_date):
                self.deserialize_history(history_record)
                for history_date, history_record in
                download_data["history"].items()
            }
            if "latestImportedDate" in download_data:
                download_data["latestImportedDate"] = ciso8601.parse_datetime(
                    download_data["latestImportedDate"],
                )

        servarr_type_map = self.SERVARR_TYPE_MAPS[servarr_config["type"]]
        dir_id_key = f"{servarr_type_map['dir_type']}Id"
        if not self.replay and dir_id is None:
            # Try to correlate to the Servarr movie/series/etc. using existing Prunerr
            # data
            for history_record in download_data["history"].values():
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
                    "No history found for %r Servarr download item %r",
                    servarr_config["name"],
                    download_item,
                )
                return self.serialize_download_data(download_data, None, data_path)
            dir_id = download_record[dir_id_key]

        # Reconcile current Servarr history with the Prunerr data file
        download_history = {}
        if servarr_history is None:
            servarr_history = self.get_dir_history(servarr_config, dir_id)
        if download_id not in servarr_history["records"]["download_ids"]:
            logger.error(
                "Download item %r not found in %r Servarr history for %r",
                download_item,
                servarr_config["name"],
                dir_id_key,
            )
        for history_record in reversed(
                servarr_history["records"]["download_ids"].get(download_id, []),
        ):
            # TODO: Skip duplicate events for multi-file items such as season packs

            # Preserve existing Prunerr data
            existing_record = download_data["history"].get(
                history_record["date"], {},
            )
            history_record["prunerr"] = existing_record.get("prunerr", {})
            # Insert into the new history keyed by time stamp
            download_history[history_record["date"]] = history_record

            # Synchronize the item's state with this history event/record
            if not self.replay and history_record["prunerr"].get("syncedDate"):
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
                logger.info(
                    "Handling %r Servarr %r event: %r",
                    servarr_config["name"],
                    history_record["eventType"],
                    download_item,
                )
                handler_result = handler(
                    servarr_config,
                    download_item,
                    history_record,
                    download_data=download_data,
                    is_realtime=is_realtime,
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

        return self.move_torrent(download_item, src_path, dst_path)

    def handle_imported(
            self,
            servarr_config,
            download_item,
            history_record,
            download_data,
            is_realtime=True,
    ):
        """
        Handle Servarr imported event, wait for import to complete, then move.
        """
        if is_realtime:
            logger.info(
                "Letting running import complete before moving: %r",
                download_item,
            )
            download_data["latestImportedDate"] = history_record["date"]
            return

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

        # If we're not waiting for history, then proceed to move the download item.
        # Ensure the download item's location matches the Servarr state
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
        try:
            return self.client.get_torrent(download_id.lower())
        except KeyError:
            # Can happen if the download client item has been manually deleted
            logger.error(
                "Could not find item in download client "
                "for Servarr imported event: %s",
                download_id,
            )

    def handle_test(self, servarr_config, **custom_script_kwargs):
        """
        Handle a Servarr `Test` event, exercise as much as possible w/o making changes.
        """
        logger.info(
            "Download client session statistics:\n%s",
            pprint.pformat(self.client.session_stats()._fields),
        )
        logger.info(
            "Servarr instance system status:\n%s",
            pprint.pformat(servarr_config["client"].system_status()._data),
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
        download_record = None
        while (
            # Is history for this Servarr instance exhausted?
            history_page is None
            or (servarr_history["page"] * 250) <= history_page["totalRecords"]
        ) and download_record is None:
            history_page = servarr_config["client"]._get(
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
                    download_record = history_record
                    break
            servarr_history["page"] += 1

        return download_record

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
        history_record = copy.deepcopy(history_record)
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
        # Convert loaded JSON to native types where possible
        if download_history is not None:
            download_history = {
                history_date.strftime(self.SERVARR_DATETIME_FORMAT):
                self.serialize_history(history_record)
                for history_date, history_record in
                download_history.items()
            }
        download_data["history"] = download_history
        if "latestImportedDate" in download_data:
            download_data["latestImportedDate"] = download_data[
                "latestImportedDate"
            ].strftime(self.SERVARR_DATETIME_FORMAT)
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

        for downloader_config in servarr_client._get("downloadclient"):
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

        # Collect the settings for the Prunerr custom script connection if present for
        # the Servarr instance.  Used to lookup the custom script path when dispatching
        # followup event subprocesses.
        servarr_config["notification"] = {}
        for connect_config in servarr_client._get("notification"):
            connect_config["fieldValues"] = field_values = {
                connect_config_field["name"]: connect_config_field["value"]
                for connect_config_field in connect_config["fields"]
                if "value" in connect_config_field
            }
            servarr_config["notification"][connect_config["name"]] = connect_config

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


def handle(prunerr):
    """
    Change download item state per a Servarr instance event as a `Custom Script`.

    For example, depending on config, imported items are moved to `./imported/`, the
    import symbolic links are added, and deleted items are moved to `./deleted`.
    """
    # Collect all environment variables with the prefix used for Servarr custom scripts
    env_var_prefix = f"{prunerr.servarr_config['type']}_"
    custom_script_kwargs = {
        prunerr.strip_type_prefix(
            prunerr.servarr_config["type"],
            env_var[len(env_var_prefix):],
        ).lower(): env_value
        for env_var, env_value in os.environ.items()
        if env_var.startswith(env_var_prefix)
    }
    logger.debug(
        "Custom script kwargs:\n%s",
        pprint.pformat(custom_script_kwargs),
    )

    try:
        result = prunerr.dispatch_event(prunerr.servarr_config, **custom_script_kwargs)
    except ServarrEventError as exc:
        result = exc

    # The Servarr Custom Script events seem to combine file deletion events on upgrade
    # which is different from the history records from the Servarr API where the import
    # and subsequent deletion are 2 distinct events.  Workaround this difference by
    # dispatching the deletion events after handling this Custom Script event.
    eventtype = custom_script_kwargs["eventtype"]
    eventtype_stripped = prunerr.strip_type_prefix(
        prunerr.servarr_config["type"],
        eventtype,
    )
    handler_suffix = prunerr.SERVARR_CUSTOM_SCRIPT_EVENT_TYPES.get(
        eventtype_stripped,
        eventtype_stripped,
    )
    if handler_suffix != "deleted" and "deletedpaths" in custom_script_kwargs:
        for deleted_path in custom_script_kwargs["deletedpaths"].split("|"):
            delete_event_kwargs = dict(
                custom_script_kwargs,
                eventtype="deleted",
                file_path=deleted_path,
            )
            # Don't know which download client item the deleted path is for.
            delete_event_kwargs.pop("download_id", None)
            logger.info("Dispatching nested Sonarr deleted event: %s", deleted_path)
            try:
                prunerr.dispatch_event(prunerr.servarr_config, **delete_event_kwargs)
            except ServarrEventError:
                logger.exception("Error handling nested deleted event")

    if isinstance(result, ServarrEventError):
        raise result

    return result


parser_handle = subparsers.add_parser("handle", help=handle.__doc__.strip())
parser_handle.add_argument(
    "servarr_name",
    help="""\
The name of the Servarr instance in the `~/.config/prunerr.yml` configuration from which
the event to handle has been dispatched.
""",
)
parser_handle.set_defaults(command=handle)


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


def main(args=None):
    logging.basicConfig(level=logging.INFO)
    # Want just our logger, not transmission-rpc's to log DEBUG
    # logger.setLevel(logging.DEBUG)
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
                pprint.pformat(results),
            )


main.__doc__ = __doc__


if __name__ == "__main__":
    main()
