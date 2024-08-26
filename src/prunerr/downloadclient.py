# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

# pylint: disable=magic-value-comparison,missing-any-param-doc,missing-param-doc
# pylint: disable=missing-raises-doc,missing-return-doc,missing-return-type-doc
# pylint: disable=missing-type-doc

"""
Prunerr interaction with download clients.
"""

import re
import shutil
import urllib.parse
import bdb
import pdb
import logging

import requests
import transmission_rpc

import prunerr.downloaditem
import prunerr.operations
from . import utils
from .utils import pathlib

logger = logging.getLogger(__name__)


class PrunerrDownloadClient:
    """
    An individual, specific download client that Prunerr interacts with.
    """

    # TODO: Make configurable?
    SEEDING_DIR_BASENAME = "seeding"
    UNREGISTERED_ERROR_RE = re.compile(r".*(not |un)registered.*")

    client: transmission_rpc.client.Client
    items: list
    operations: prunerr.operations.PrunerrOperations

    def __init__(self, runner):
        """
        Capture references to the runner and individual download client configuration.
        """
        self.runner = runner
        self.config = {}
        self.servarrs = {}
        self.verifying_items = {}

    def __repr__(self):
        """
        Readable, informative, and specific representation to ease debugging.
        """
        return f"<{type(self).__name__} at {self.config.get('name')!r}>"

    def update(self, config):
        """
        Update configuration, connect the RPC client, and update the list of items.
        """
        self.config = config

        if not self.config.get("url"):
            raise utils.PrunerrValidationError(
                "Download client configuration must include a URL under"
                f" `download-clients/*/url`: {self.runner.config_file}"
            )

        # Pull defaults from the example configuration:
        example_confg = next(
            iter(self.runner.example_confg["download-clients"].values()),
        )
        self.config.setdefault(
            "max-download-bandwidth",
            example_confg["max-download-bandwidth"],
        )
        self.config.setdefault(
            "min-download-time-margin",
            example_confg["min-download-time-margin"],
        )

        self.config.setdefault(
            "password",
            urllib.parse.urlsplit(self.config["url"]).password,
        )
        self.config["url"] = utils.normalize_url(self.config["url"])

        # Configuration specific to Prunerr, IOW not taken from the download client
        self.config["min-free-space"] = calc_free_space_margin(self.config)
        self.operations = prunerr.operations.PrunerrOperations(
            self,
            self.runner.config.get("indexers", {}),
        )

        # Connect to the download client's RPC API, also retrieves session data
        split_url = urllib.parse.urlsplit(self.config["url"])
        # Normalize the port for URLs without one specified:
        if not (port := split_url.port):
            if split_url.scheme == "http":
                port = 80
            elif split_url.scheme == "https":
                port = 443
            else:
                raise ValueError(
                    f"Could not guess port from URL: {self.config['url']}",
                )
        logger.debug(
            "Connecting to download client: %s",
            self.config["url"],
        )
        self.client = transmission_rpc.client.Client(
            protocol=split_url.scheme,
            host=split_url.hostname,
            port=port,
            path=split_url.path,
            username=split_url.username,
            password=self.config["password"],
            timeout=self.config.get(
                "timeout",
                transmission_rpc.constants.DEFAULT_TIMEOUT,
            ),
        )

        # Update any Servarr references or data that depends on the download client
        # session data
        for servarr_url in config.get("servarrs", set()):
            self.servarrs[servarr_url] = self.runner.servarrs[
                servarr_url
            ].download_clients[self.config["url"]]
            self.servarrs[servarr_url].seeding_dir = prunerr.downloaditem.parallel_to(
                self.client.session.download_dir,
                self.servarrs[servarr_url].download_dir,
                self.SEEDING_DIR_BASENAME,
            )

        # Retrieve any information from the download client's RPC API needed for all
        # sub-commands
        logger.debug(
            "Retrieving list of download items from download client: %s",
            self.config["url"],
        )
        self.items = [
            prunerr.downloaditem.PrunerrDownloadItem(
                self,
                torrent._client,  # pylint: disable=protected-access
                torrent,
            )
            # TODO: Reduce memory consumption, narrow the list of fields requested for
            # all items.  Maybe also have separate sets of fields for operations done
            # on the whole list of items (e.g. filtering to find seeding items) and
            # operations on individual torrents (e.g. review).
            for torrent in self.client.get_torrents()
        ]
        return self.items

    # Sub-commands

    def review(self, servarr_queue):
        """
        Apply configured review operations to all download items.
        """
        # TODO: Maybe handle multiple downloading items for the
        # same Servarr item such as when trying several to see which
        # ones actually have decent download speeds?
        results = {}
        # Need to make a copy in case review leads to deleting an item and modifying
        # `self.items`.
        download_dir = pathlib.Path(self.client.session.download_dir)
        for item in [item for item in self.items if download_dir in item.path.parents]:
            item_results = None
            queue_record = servarr_queue.get(item.hashString.upper(), {})
            try:
                item_results = item.review(queue_record)
            except utils.RETRY_EXC_TYPES:
                logger.exception(
                    "Error reviewing item: %s",
                    item,
                )
            if item_results:
                results[item.hashString] = item_results
        return results

    def re_add(self) -> list:
        """
        Remove and re-add all download items with nothing downloaded.

        :return: List all the items that were re-added to the download client.
        """
        seeding_dir = (
            pathlib.Path(self.client.session.download_dir).parent
            / self.SEEDING_DIR_BASENAME
        )
        # Transmission seems to verify items in the order of their indexes, in the order
        # they were added, so reverse the order to avoid clashing with items in the
        # process of verifying:
        re_add_results = []
        for item in reversed(self.items):
            # Skip items from the older full-list response first for speed:
            if not item.re_add_check(seeding_dir):  # pragma: no cover
                continue
            # Also get the latest item data in case it has finished verifying while
            # previous items were re-added:
            item.update()
            if not item.re_add_check(seeding_dir):  # pragma: no cover
                logger.debug(
                    "Not re-adding download item whose metadata changed: %r",
                    item,
                )
                continue
            re_add_results.append(item.re_add().name)
        return re_add_results

    # Other, non-sub-command methods

    def sort_items_by_tracker(self, items):
        """
        Sort the given download items according to the indexer priority operations.
        """
        return sorted(
            items,
            # remove lowest priority and highest ratio first
            key=lambda item: self.operations.exec_indexer_operations(item)[1],
            reverse=True,
        )

    # Methods used by the `free-space` sub-command

    def delete_files(self, item):
        """
        Delete all files and directories for the given path and stat or download item.

        First remove from the download client if given a download item.

        :param item: A `pathlib.Path()` filesystem path or a download item to be
            deleted.
        """
        # Handle actual items recognized by the download client
        if isinstance(item, prunerr.downloaditem.PrunerrDownloadItem):
            size = item.disk_usage
            self.operations.exec_indexer_operations(item)
            logger.info(
                "Deleting %r: free space -> %0.2f %s",
                item,
                *transmission_rpc.utils.format_size(
                    self.client.session.download_dir_free_space + size,
                ),
            )

            # When freeing disk space it's important not to get hung up waiting for a
            # heavily loaded client. Be very defensive and proceed directly to deleting
            # the data:
            self.client.remove_torrent(
                [item.hashString],
                timeout=transmission_rpc.constants.DEFAULT_TIMEOUT,
            )
            self.items.remove(item)
            # Remove each item file whether in the `download-dir` or the
            # `incomplete-dir`:
            for item_file in item.files:
                if item_file.path.exists():  # pragma: no cover
                    item_file.path.unlink()
                # Also remove the ancestor directories if they're not empty:
                file_parent = item_file.path.parent
                while [  # pylint: disable=while-used
                    parent for parent in item.parents if parent in file_parent.parents
                ]:
                    if next(file_parent.iterdir(), None) is None:  # pragma: no cover
                        file_parent.rmdir()
                    file_parent = file_parent.parent

        # Handle filesystem paths not recognized by the download client
        else:
            path, stat = item
            size = (stat.st_blocks * 512) if (stat.st_nlink == 1) else 0
            logger.info(
                "Deleting %r, %0.2f %s: free space -> %0.2f %s",
                str(path),
                *(
                    transmission_rpc.utils.format_size(size)
                    + transmission_rpc.utils.format_size(
                        self.client.session.download_dir_free_space + size,
                    )
                ),
            )

            # Delete the actual files ourselves to workaround Transmission hanging when
            # deleting the data of large items: e.g. season packs.
            if path.is_dir():  # pragma: no cover
                shutil.rmtree(path, onerror=log_rmtree_error)
            elif path.exists():
                path.unlink()
            else:  # pragma: no cover
                # Under high download client load, the deletion from the client
                # sometimes seems to fail but Prunerr successfully deletes the data. On
                # the next `daemon` loop Prunerr will try to delete it from the client
                # again, which is correct, but then chokes on the missing files it
                # already deleted.
                logger.error(
                    "Path to be deleted doesn't exist: %s",
                    path,
                )
            if next(path.parent.iterdir(), None) is None:  # pragma: no cover
                # The directory containging the file is empty
                path.parent.rmdir()

        # Refresh the sessions data including free space.
        # TODO: Until we aggregate download client directories by `*.stat().st_dev`, we
        # can't know which of their sessions to update when we delete a path.  Maybe
        # implement?  Premature optimization?
        for download_client in self.runner.download_clients.values():
            download_client.client.get_session()

        return size

    def try_delete_files(self, item):
        """
        Attempt to delete a path or a download item, but tolerate and log failures.

        :param item: A `pathlib.Path()` filesystem path or a download item to be
            deleted.
        """
        try:
            return self.delete_files(item)
        except transmission_rpc.error.TransmissionTimeoutError:  # pragma: no cover
            logger.debug(
                "Expected short timeout to promptly free space: %r",
                item,
                exc_info=True,
            )
        except (
            Exception  # pylint: disable=broad-exception-caught
        ) as exc_value:  # pragma: no cover
            if isinstance(
                exc_value,
                (KeyboardInterrupt, AssertionError, bdb.BdbQuit, pdb.Restart),
            ):
                raise
            logger.exception(
                "Unexpected exception removing item, freeing space anyways: %r",
                item,
            )
        return 0  # pragma: no cover

    def free_space_check(self):
        """
        Determine if there's sufficient free disk space.
        """
        total_remaining_download = sum(
            item.leftUntilDone for item in self.items if item.status == "downloading"
        )
        if total_remaining_download > self.client.session.download_dir_free_space:
            logger.debug(
                "Total size of remaining downloads is greater than the available free "
                "space: %0.2f %s - %0.2f %s = %0.2f %s",
                *(
                    transmission_rpc.utils.format_size(total_remaining_download)
                    + transmission_rpc.utils.format_size(
                        self.client.session.download_dir_free_space
                    )
                    + transmission_rpc.utils.format_size(
                        total_remaining_download
                        - self.client.session.download_dir_free_space
                    )
                ),
            )
        if self.client.session.download_dir_free_space >= self.config["min-free-space"]:
            logger.debug(
                "Sufficient free space to continue downloading: "
                "%0.2f %s - %0.2f %s = %0.2f %s",
                *(
                    transmission_rpc.utils.format_size(
                        self.client.session.download_dir_free_space,
                    )
                    + transmission_rpc.utils.format_size(
                        self.config["min-free-space"],
                    )
                    + transmission_rpc.utils.format_size(
                        self.client.session.download_dir_free_space
                        - self.config["min-free-space"],
                    )
                ),
            )
            return True
        logger.debug(
            "Insufficient free space to continue downloading: "
            "%0.2f %s - %0.2f %s = %0.2f %s",
            *(
                transmission_rpc.utils.format_size(
                    self.config["min-free-space"],
                )
                + transmission_rpc.utils.format_size(
                    self.client.session.download_dir_free_space,
                )
                + transmission_rpc.utils.format_size(
                    self.config["min-free-space"]
                    - self.client.session.download_dir_free_space,
                )
            ),
        )
        return False

    def find_unregistered(self):  # noqa: V105
        """
        Filter already imported items that are no longer recognized by their tracker.

        For example, when a private tracker removes a duplicate/invalid/unauthorized
        item.
        """
        # TODO: Mark as failed in Servarr?
        seeding_dirs = [servarr.seeding_dir for servarr in self.servarrs.values()]
        return self.sort_items_by_tracker(
            item
            for item in self.items
            if (
                (
                    item.status == "downloading"
                    # Give seeding items time to be imported by Servarr since they've
                    # already been fully downloaded.
                    or [
                        seeding_dir
                        for seeding_dir in seeding_dirs
                        if seeding_dir in item.path.parents
                    ]
                )
                and item.error == 2
                and self.UNREGISTERED_ERROR_RE.match(item.errorString.lower())
                is not None
            )
        )

    def find_seeding(self):  # noqa: V105
        """
        Filter items that have not yet been imported by Servarr, order by priority.
        """
        seeding_dir = (
            pathlib.Path(self.client.session.download_dir).parent
            / self.SEEDING_DIR_BASENAME
        )
        return self.sort_items_by_tracker(
            item
            for item in self.items
            # only those previously acted on by Servarr and moved
            if item.status == "seeding"
            and seeding_dir in item.path.parents
            and self.operations.exec_indexer_operations(item)[0]
        )

    def verify_corrupt_items(self):
        """
        Verify and resume download items flagged as having corrupt data.
        """
        corrupt_items = {
            item.hashString: item
            for item in self.items
            if item.hashString not in self.verifying_items
            and item.error == 3
            and (
                "verif" in item.errorString.lower()
                or "corrput" in item.errorString.lower()
            )
        }
        if corrupt_items:
            logger.info(
                "Verifying corrupt download items:\n  %s",
                "\n  ".join(repr(item) for item in corrupt_items.values()),
            )
            self.client.verify_torrent(list(corrupt_items.keys()))
            self.verifying_items.update(corrupt_items)
            return list(corrupt_items.keys())
        return None

    def resume_verified_items(self):
        """
        Resume downloading any previously corrupt items that have finished verifying.
        """
        for verifying_item in self.verifying_items.values():
            verifying_item.update()
        verified_items = {
            item_hash: verifying_item
            for item_hash, verifying_item in self.verifying_items.items()
            if not verifying_item.status.startswith("check")
        }
        if verified_items:
            logger.info(
                "Resuming verified download items:\n  %s",
                "\n  ".join(repr(item) for item in verified_items.values()),
            )
            self.client.start_torrent(list(verified_items.keys()))
            for item_hash in verified_items.keys():
                del self.verifying_items[item_hash]
        return verified_items

    def add_torrent(self, download_url, **kwargs):
        """
        Add a torrent to the download client and update instance state.

        :param download_url: The URL from which to download the torrent to add.
        :return: The added ``prunerr.downloaditem.PrunerrDownloadItem()`` instance.
        """
        logger.info("Downloading torrent: %s", download_url)
        response = requests.get(download_url, timeout=5, stream=True)
        response.raise_for_status()
        added_torrent = prunerr.downloaditem.PrunerrDownloadItem(
            self,
            self.client,  # pylint: disable=protected-access
            self.client.add_torrent(torrent=response.raw, **kwargs),
        )
        self.items.append(added_torrent)
        return added_torrent


class DownloadClientTimeout(Exception):
    """A download client operation took too long."""


def config_from_url(auth_url):
    """
    Normalize download client URLs for the port and without the password.

    Used for matching with Servarr download clients.
    """
    auth_url_split = urllib.parse.urlsplit(auth_url)
    url = utils.normalize_url(auth_url)
    return {"url": url, "password": auth_url_split.password}


def calc_free_space_margin(config):
    """
    Calculate an appropriate margin of disk space to keep free.

    Used when deciding whether to delete download items and their files in the
    `free-space` sub-command based on the maximum download bandwidth/speed in Mbps and
    the amount of time in seconds at that rate for which download clients should be able
    to continue downloading without exhausting disk space.
    """
    return (
        (
            # Convert bandwidth bits to bytes
            config["max-download-bandwidth"]
            / 8
        )
        * (
            # Convert bandwidth MBps to Bps
            1024
            * 1024
        )
        * (
            # Multiply by seconds of download time margin
            config["min-download-time-margin"]
        )
    )


# TODO: Not sure how to test this, but if there's a way, we should add coverage
def log_rmtree_error(function, path, excinfo):  # pragma: no cover
    """
    Inform the user on errors deleting item files but also proceed to delete the rest.

    Error handler for `shutil.rmtree`.
    """
    logger.error(
        "Error removing %r (%s)",
        path,
        ".".join((function.__module__, function.__name__)),
        exc_info=excinfo,
    )
