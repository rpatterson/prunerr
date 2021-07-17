#!/usr/bin/env python
"""
Remove Servarr download client items to preserve disk space according to rules.
"""

import sys
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

import dateutil.parser
import humps
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

    # Map the different Servarr applications to values that differ between them
    SERVARR_CLIENT_TYPES = dict(sonarr=arrapi.SonarrAPI, radarr=arrapi.RadarrAPI,)
    SERVARR_DOWNLOAD_DIR_FIELDS = dict(sonarr="tvDirectory", radarr="movieDirectory",)
    # Map Servarr event types from the API to those used in the custom scripts
    SERVARR_CUSTOM_SCRIPT_EVENT_TYPES = {
        "grabbed": "Grab",
        "downloadFolderImported": "Download",
        "episodeFileRenamed": "Rename",
        "movieFileRenamed": "Rename",
        "episodeFileDeleted": "EpisodeDeleted",
        "movieFileDeleted": "MovieDeleted",
    }
    SERVARR_SCRIPT_CUSTOM_EVENT_DISPATCH = {
        "Grab": "grabbed",
        "Download": "imported",
        "Rename": "renamed",
        "EpisodeDeleted": "deleted",
        "MovieDeleted": "deleted",
    }
    # Map any Servarr API JSON keys to the custom script environment variables that
    # can't be derrived automatically
    SERVARR_CUSTOM_SCRIPT_KWARGS = dict(
        # Extracted from https://wiki.servarr.com/en/sonarr/custom-scripts
        # deletedpaths=None
        # deletedrelativepaths=None
        # download_client=None
        # download_id=None
        # episodefile_episodeairdates=None
        # episodefile_episodeairdatesutc=None
        # episodefile_episodecount=None
        # episodefile_episodeids=None
        # episodefile_episodenumbers=None
        # episodefile_episodetitles=None
        # episodefile_id=None
        # episodefile_path=None
        # episodefile_quality=None
        # episodefile_qualityversion=None
        # episodefile_relativepath=None
        # episodefile_releasegroup=None
        # episodefile_scenename=None
        # episodefile_seasonnumber=None
        # episodefile_sourcefolder=None
        # episodefile_sourcepath=None
        # eventtype=None
        # health_issue_level=None
        # health_issue_message=None
        # health_issue_type=None
        # health_issue_wiki=None
        # isupgrade=None
        # release_absoluteepisodenumbers=None
        # release_episodeairdates=None
        # release_episodeairdatesutc=None
        # release_episodecount=None
        # release_episodenumbers=None
        # release_episodetitles=None
        # release_indexer=None
        # release_quality=None
        # release_qualityversion=None
        # release_releasegroup=None
        # release_seasonnumber=None
        # release_size=None
        # release_title=None
        # series_deletedfiles=None
        # series_id=None
        # series_imdbid=None
        # series_path=None
        # series_title=None
        # series_tvdbid=None
        # series_tvmazeid=None
        # series_type=None
    )

    def __init__(self, config, servarrs, client, url):
        """
        Do any config post-processing and set initial state.
        """
        # Download client handling
        self.client = client
        self.url = url
        session = self.client.get_session()

        # Prunerr config processing
        self.config = config
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

        # Servarr API client and download client settings
        self.servarrs = servarrs
        # Derive the destination directories for this download client for each type of
        # Servarr instance, e.g. `tvDirectory` vs `movieDirectory`.
        for servarr_config in self.servarrs.values():
            servarr_config["downloadDir"] = pathlib.Path(
                servarr_config["downloadclient"]["fieldValues"][
                    self.SERVARR_DOWNLOAD_DIR_FIELDS[servarr_config["type"]]
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

        # Initial state
        self.popen = self.copying = None
        self.corrupt = {}

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
        self.torrents = self.client.get_torrents(
            arguments=(
                "id",
                "hashString",
                "name",
                "status",
                "error",
                "errorString",
                "trackers",
                "bandwidthPriority",
                "downloadDir",
                "leftUntilDone",
                "sizeWhenDone",
                "totalSize",
                "progress",
                "uploadRatio",
                "priorities",
                "wanted",
                "files",
            )
        )

    def list_torrent_files(self, torrent, download_dir=None):
        """
        Iterate over all torrent selected file paths that exist.
        """
        if download_dir is None:
            download_dir = torrent.downloadDir

        torrent_files = torrent.files()
        assert torrent_files, "Must be able to find torrent files"

        return (
            file_["name"]
            for file_ in torrent_files.values()
            if file_.get("selected")
            and os.path.exists(os.path.join(download_dir, file_["name"]))
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

            try:
                self.exec_()
            except socket.error:
                logger.exception("Connection error while running daemon")
                pass

            # Wait for the next interval
            start = time.time()
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
        Sort the given torrents based upon tracker priority and other metrics.
        """
        trackers_ordered = [
            hostname
            for hostname, priority in reversed(
                self.config["indexers"]["priorities"],
            )
        ]
        return sorted(
            ((index, torrent) for index, torrent in enumerate(torrents)),
            # remove lowest priority and highest ratio first
            key=lambda item: self.get_torrent_priority_key(trackers_ordered, item[1]),
        )

    def lookup_tracker_priority(self, torrent):
        """
        Determine which tracker hostname and priority apply to the torrent if any.
        """
        # TODO: abstract tracker to indexer with priorities from servarr API
        for tracker in torrent.trackers:
            for action in ("announce", "scrape"):
                parsed = urllib.parse.urlsplit(tracker[action])
                for hostname, priority in self.config["indexers"]["priorities"]:
                    if parsed.hostname and parsed.hostname.endswith(hostname):
                        return hostname, priority
        return None, None

    def get_torrent_priority_key(self, trackers_ordered, torrent):
        """
        Combine tracker ranking, torrent priority, and ratio into a sort key.
        """
        hostname, priority = self.lookup_tracker_priority(torrent)
        traker_rank = -1
        if hostname in trackers_ordered:
            traker_rank = trackers_ordered.index(hostname)
        return (
            traker_rank,
            torrent.bandwidthPriority,
            -torrent.ratio,
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
                hostname, priority = self.lookup_tracker_priority(candidate)
                logger.info(
                    "Deleting seeding %s to free space, "
                    "%0.2f %s + %0.2f %s: tracker=%s, priority=%s, ratio=%0.2f",
                    candidate,
                    *(
                        utils.format_size(session.download_dir_free_space)
                        + utils.format_size(candidate.totalSize)
                        + (hostname, candidate.bandwidthPriority, candidate.ratio)
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
        for entry in os.listdir(path):
            entry_path = os.path.join(path, entry)
            # TODO: exclude valid import links
            if entry_path not in torrent_paths and entry_path not in torrent_dirs:
                du.stdin.write(entry_path + "\0")
                du_line = du.stdout.readline()
                size, du_path = du_line[:-1].split("\t", 1)[:2]
                size = int(size)
                yield (int(size), entry_path)
            elif entry_path in torrent_dirs:
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
        )

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

        # Move any non-torrent files managed by Prunerr
        # Explicit is better than implicit, specific e.g.: if a user has manually
        # extracted an archive in the old import location we want the orphan logic to
        # find it after Servarr has upgraded it
        old_download_path = pathlib.Path(download_dir)
        torrent_stem_path = old_download_path / torrent.name
        if (pathlib.Path(torrent.downloadDir) / torrent.name).is_file():
            torrent_stem_path = torrent_stem_path.parent / torrent_stem_path.stem
        for import_link in glob.glob(
            f"{glob.escape(torrent_stem_path)}**-servarr-imported.ln", recursive=True,
        ):
            import_link_path = pathlib.Path(import_link)
            import_link_relative = import_link_path.relative_to(old_path)
            import_link_dest = pathlib.Path(new_path) / import_link_relative
            shutil.move(import_link, import_link_dest)
            if import_link_path.parent != pathlib.Path(old_path) and not list(
                import_link_path.parent.iterdir()
            ):
                import_link_path.parent.rmdir()  # empty dir

        return torrent_location

    def sync(self):
        """
        Move torrents that have already been successfully imported as appropriate.

        Ensure that the location/state of download client items is as close to what it
        would be if the items had been processed through the default `event` sub-command
        as a Servarr `Custom Script` as per the history in the Servarr instances.  IOW,
        imported items are moved to `./imported/`, the import symbolic links are in
        place, and deleted items are moved to `./deleted`.
        """
        event_results = {}
        for torrent in self.torrents:
            if torrent.status != "seeding":
                # Not finished downloading, no changes needed
                continue

            # Determine the root path for all files in this torrent
            download_path = (
                pathlib.Path(torrent.download_dir)
                / pathlib.Path(torrent.files()[0].name).parts[0]
            ).resolve()

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
                # instance.  Collect the Servarr history for this download client item.
                torrent_history = self.find_item_history(
                    servarr_config, torrent=torrent
                )

                if not torrent_history:
                    logger.error(
                        "No history found for %r Servarr download item %r",
                        servarr_config["url"],
                        torrent,
                    )
                    break

                for history_record in reversed(torrent_history):
                    custom_script_kwargs = dict(
                        eventtype=self.SERVARR_CUSTOM_SCRIPT_EVENT_TYPES.get(
                            history_record["eventType"], history_record["eventType"],
                        ),
                    )
                    # Reproduuce the Sonarr custom script environment variables from the
                    # Servarr API JSON
                    for history_data in (history_record, history_record["data"]):
                        custom_script_kwargs.update(
                            (
                                self.SERVARR_CUSTOM_SCRIPT_KWARGS.get(
                                    humps.decamelize(api_key), humps.decamelize(api_key)
                                ),
                                api_value,
                            )
                            for api_key, api_value in history_data.items()
                            if not (
                                history_data is history_record and api_key == "data"
                            )
                        )
                    # Dispatch to the Servarr custom script handler for this Servarr
                    # event type
                    try:
                        history_record["prunerr_result"] = self.dispatch_event(
                            servarr_config, **custom_script_kwargs
                        )
                    except ServarrEventError:
                        # Synchronizing events that have previously been handled is the
                        # expected case here, so capture those exceptions and log them
                        # as informative messages instead of errors.
                        logger.info("%s", sys.exc_info()[1])
                    event_results.setdefault(torrent.hashString, {}).setdefault(
                        servarr_config["name"], []
                    ).append(history_record)

    def dispatch_event(self, servarr_config, eventtype, **custom_script_kwargs):
        """
        Handle a Servarr event after custom script env vars transformed to kwargs.
        """
        handler_suffix = self.SERVARR_SCRIPT_CUSTOM_EVENT_DISPATCH.get(
            eventtype,
            eventtype.lower(),
        )
        handler_name = f"handle_{handler_suffix}"
        logger.debug(
            "Custom script kwargs:\n%s",
            pprint.pformat(custom_script_kwargs),
        )
        if hasattr(self, handler_name):
            handler = getattr(self, handler_name)
            logger.info(
                "Handling %r Servarr %r event",
                servarr_config["name"],
                eventtype,
            )
            return handler(servarr_config, **custom_script_kwargs)

        logger.warning(
            "No handler found for Servarr %r event type: %s",
            servarr_config["name"],
            eventtype,
        )

    def handle_grabbed(self, servarr_config, download_id, **custom_script_kwargs):
        """
        Handle a Servarr grabbed event, confirm the item received by download client.
        """
        torrent = self.client.get_torrent(download_id.lower())
        torrent_path = pathlib.Path(torrent.download_dir) / torrent.name
        session = self.client.get_session()
        downloads_dir = self.config["downloaders"].get(
            "download-dir",
            os.path.join(os.path.dirname(session.download_dir), "downloads"),
        )
        if pathlib.Path(downloads_dir) in torrent_path.parents:
            return torrent
        else:
            raise ServarrEventError(
                f"Grabbed download item {torrent!r} not in Servarr downloads "
                f"directory: {torrent.download_dir}"
            )

    def handle_imported(
            self,
            servarr_config,
            download_id,
            dropped_path,
            imported_path,
            **custom_script_kwargs,
    ):
        """
        Handle a Servarr imported event, move the item data to the imported directory.
        """
        torrent = self.client.get_torrent(download_id.lower())
        session = self.client.get_session()
        torrent_path = pathlib.Path(torrent.download_dir) / torrent.name
        downloads_dir = self.config["downloaders"].get(
            "download-dir",
            os.path.join(os.path.dirname(session.download_dir), "downloads"),
        )
        imported_dir = self.config["downloaders"].get(
            "imported-dir",
            os.path.join(os.path.dirname(session.download_dir), "imported"),
        )

        # Move the download item to the location appropriate for it's Servarr state
        if pathlib.Path(imported_dir) not in torrent_path.parents:
            self.move_torrent(torrent, old_path=downloads_dir, new_path=imported_dir)
        else:
            raise ServarrEventError(
                f"Imported download item {torrent!r} already in Servarr imported "
                f"directory: {torrent.download_dir}"
            )

        # Reflect imported files in the download client item using symbolic links
        old_dropped_path = pathlib.Path(dropped_path)
        if servarr_config["downloadDir"] not in old_dropped_path.parents:
            logger.error(
                "Servarr dropped path %r not in download client's download directory %r"
                "for %r",
                dropped_path,
                servarr_config["downloadDir"],
                torrent,
            )
            return torrent
        relative_to_download_dir = old_dropped_path.relative_to(
            servarr_config["downloadDir"],
        )
        new_dropped_path = torrent.downloadDir / relative_to_download_dir
        link_path = (
            new_dropped_path.parent / f"{new_dropped_path.stem}-servarr-imported.ln"
        )
        imported_link_target = pathlib.Path(
            os.path.relpath(imported_path, link_path.parent)
        )
        if link_path.exists():
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
        else:
            logger.info(
                "Symlinking imported file: %s -> %s", link_path, imported_link_target,
            )
            if not imported_link_target.is_file():
                logger.error(
                    "Symlink download file to imported file that doesn't exist: "
                    "%s -> %s",
                    link_path,
                    imported_link_target,
                )
            link_path.symlink_to(imported_link_target)

        return torrent

    def handle_deleted(self, servarr_config, source_title, **custom_script_kwargs):
        """
        Handle a Servarr deleted event, move the item data to the deleted directory.

        Leave import symlinks in place so that broken symlinks can be used as an
        indicator of which imported files have been upgraded for items that contain
        multiple imported files.
        """
        self.find_item_history(servarr_config, import_path=source_title)
        torrent = self.client.get_torrent(
            servarr_config["history"]["event_types"]["source_titles"][source_title][
                "downloadFolderImported"
            ][0]["downloadId"].lower()
        )
        torrent_path = pathlib.Path(torrent.download_dir) / torrent.name
        session = self.client.get_session()
        imported_dir = self.config["downloaders"].get(
            "imported-dir",
            os.path.join(os.path.dirname(session.download_dir), "imported"),
        )
        deleted_dir = self.config["downloaders"].get(
            "deleted-dir",
            os.path.join(os.path.dirname(session.download_dir), "deleted"),
        )
        if pathlib.Path(deleted_dir) not in torrent_path.parents:
            self.move_torrent(torrent, old_path=imported_dir, new_path=deleted_dir)
            torrent.update()
            return torrent
        else:
            raise ServarrEventError(
                f"Deleted download item {torrent!r} already in Servarr deleted "
                f"directory: {torrent.download_dir}"
            )

    def find_item_history(self, servarr_config, torrent=None, import_path=None):
        """
        Find the most recent Servarr history for the given torrent.

        Cache history from the Servarr API endpoint as we page through the history
        across subsequent calls.
        """
        if (torrent is None and import_path is None) or (
            torrent is not None and import_path is not None
        ):
            raise ValueError(
                "Must provide one of a download client item torrent object "
                "or a filesystem path to a Servarr imported item"
            )

        servarr_history = servarr_config.setdefault(
            "history",
            dict(
                page=1,
                records=dict(download_ids={}, source_titles={}),
                event_types=dict(download_ids={}, source_titles={}),
            ),
        )

        if (
                import_path is not None
                and "downloadFolderImported" in servarr_history["event_types"][
                    "source_titles"
                ].get(import_path, {})
        ):
            # Has previously retrieved history already identified the download item for
            # this imported file?
            torrent = self.client.get_torrent(
                servarr_history["event_types"]["source_titles"][import_path][
                    "downloadFolderImported"
                ][0]["downloadId"].lower()
            )

        # Page through history until a Servarr import event is found for this download
        # item.
        history_page = None
        while (
            # Is history for this Servarr instance exhausted?
            history_page is None
            or (servarr_history["page"] * 250) <= history_page["totalRecords"]
        ) and (
            (
                torrent is not None
                and "grabbed"
                not in servarr_history["event_types"]["download_ids"].get(
                    torrent.hashString.lower(), {}
                )
            )
            or (
                import_path is not None
                and "grabbed"
                not in servarr_history["event_types"]["source_titles"].get(
                    import_path, {}
                )
            )
        ):
            history_page = servarr_config["client"]._get(
                "history",
                # Maximum Servarr page size
                pageSize=250,
                page=servarr_history["page"],
            )
            for history_record in history_page["records"]:

                if (
                    torrent is not None
                    and "grabbed"
                    in servarr_history["event_types"]["download_ids"].get(
                        torrent.hashString.lower(), {}
                    )
                ) or (
                    import_path is not None
                    and "grabbed"
                    in servarr_history["event_types"]["source_titles"].get(
                        import_path, {}
                    )
                ):
                    # Already found the most recent grab for this download client item.
                    # Stop accruing history for this download client item.
                    continue

                # Perform any data transformations, e.g. to native Python types
                for history_data in (history_record, history_record["data"]):
                    for key, value in history_data.items():
                        if key.lower().endswith("date"):
                            history_data[key] = dateutil.parser.parse(value)

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

                    # TODO: if torrent is None

            servarr_history["page"] += 1
        return servarr_history["records"]["download_ids"].get(
            torrent.hashString.lower()
        )

    def reimport_seeding(self):
        """
        Re-import all seeding torrents managed by the `daemon` command.

        Move all imorted torrents back to the downloads directory so they can be
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

    # Connect clients to all download clients
    downloaders = {}
    for servarr_config in config["servarrs"]:
        servarr_config["client"] = servarr_client = Prunerr.SERVARR_CLIENT_TYPES[
            servarr_config["type"]
        ](servarr_config["url"], servarr_config["api-key"],)

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
                f"{field_values['host']}:{field_values['port']}",
                field_values["urlBase"],
                None,
                None,
            )
            # Aggregate the download clients from all Servarrs so that we run for each
            # download client once even when used for multiple Servarr instances
            if downloader_url.geturl() not in downloaders:
                downloader_config["client"] = transmission_rpc.client.Client(
                    protocol=downloader_url.scheme,
                    host=downloader_url.hostname,
                    port=downloader_url.port,
                    path=downloader_url.path,
                    username=field_values["username"],
                    password=field_values["password"],
                )
                downloader_config["servarrs"] = {}
                downloaders[downloader_url.geturl()] = downloader_config
            else:
                downloader_config = downloaders[downloader_url.geturl()]
            downloader_config["servarrs"][servarr_config["url"]] = servarr_config

    return downloaders


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
parser_sync.set_defaults(command=sync)

# TODO: Delete and blacklist torrents containing archives


def main(args=None):
    logging.basicConfig(level=logging.INFO)
    # Want just our logger, not transmission-rpc's to log INFO
    logger.setLevel(logging.INFO)
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
        prunerr_kwargs["servarrs"] = downloader_config["servarrs"]
        prunerr_kwargs["client"] = downloader_config["client"]
        prunerr_kwargs["url"] = downloader_url
        prunerr = Prunerr(**prunerr_kwargs)
        results = parsed_args.command(prunerr)
        if results:
            if isinstance(results, list):
                results = len(results)
            logger.info(
                "%r results for download client %r: %r",
                parsed_args.command.__name__,
                downloader_url,
                results,
            )


main.__doc__ = __doc__


if __name__ == "__main__":
    main()
