# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT


"""
Prunerr interaction with download clients.
"""

import typing
import collections
import re
import datetime
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
from .utils import cached_property

root_logger = logging.getLogger()
logger = logging.getLogger(__name__)


class PrunerrDownloadClient(  # pylint: disable=too-many-instance-attributes
    utils.PrunerrComponent
):
    """
    An individual, specific download client that Prunerr interacts with.
    """

    # TODO: Make configurable?
    SEEDING_DIR_BASENAME = "seeding"
    UNREGISTERED_ERROR_RE = re.compile(r".*(not |un)registered.*")

    client: transmission_rpc.client.Client
    download_dir: pathlib.Path
    seeding_dir: pathlib.Path
    incomplete_dir: typing.Optional[pathlib.Path] = None
    items_requested: datetime.datetime

    def __init__(self, runner):
        """
        Capture references to the runner and individual download client configuration.
        """
        self.runner = runner
        self.config = {}
        self.servarrs = {}
        self.verifying_items = {}

    @property
    def details(self) -> dict:
        """
        Assemble all available useful information.

        :return: Map descriptive names to useful values.
        """
        return {"name": self.config.get("name")}

    def update(self, config: dict):  # type: ignore # pylint: disable=arguments-differ
        """
        Update configuration, connect the RPC client, and update the list of items.

        :param config: The Prunerr configuration for this download client.
        :raises utils.PrunerrValidationError: The YAML configuration file has a problem
        """
        super().update()
        self.config = config

        if not self.config.get("url"):
            raise utils.PrunerrValidationError(
                "Download client configuration must include a URL under"
                f" `download-clients/*/url`: {self.runner.config_file}"
            )

        # Pull defaults from the example configuration:
        example_config = next(
            iter(self.runner.example_config["download-clients"].values()),
        )
        self.config.setdefault(
            "max-download-bandwidth",
            example_config["max-download-bandwidth"],
        )
        self.config.setdefault(
            "min-download-time-margin",
            example_config["min-download-time-margin"],
        )

        self.config.setdefault(
            "password",
            urllib.parse.urlsplit(self.config["url"]).password,
        )
        self.config["url"] = utils.normalize_url(self.config["url"])

        # Configuration specific to Prunerr, IOW not taken from the download client
        self.config["min-free-space"] = calc_free_space_margin(self.config)

        # Connect to the download client's RPC API, also retrieves session data
        split_url = urllib.parse.urlsplit(self.config["url"])
        # Normalize the port for URLs without one specified:
        if not (port := split_url.port):
            if split_url.scheme == utils.URL_SCHEME_HTTP:
                port = utils.URL_PORT_HTTP
            elif split_url.scheme == utils.URL_SCHEME_HTTPS:
                port = utils.URL_PORT_HTTPS
            else:
                raise utils.PrunerrValidationError(
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
        self.download_dir = pathlib.Path(self.client.session.download_dir)
        self.seeding_dir = self.download_dir.with_name(self.SEEDING_DIR_BASENAME)
        if self.client.session.incomplete_dir_enabled:  # pragma: no cover
            self.incomplete_dir = pathlib.Path(self.client.session.incomplete_dir)

        # Update any Servarr references or data that depends on the download client
        # session data
        for download_dir, servarr_download_client in config.get("servarrs", {}).items():
            self.servarrs[download_dir] = servarr_download_client
            servarr_download_client.update_download_client(self)

    @cached_property
    def managed_dirs(self) -> list:
        """
        Determine which directories are the top-level ancestors of files and items.

        Used to determine how far "up" the chain of ancestors to delete empty
        directories when deleting items or orphans.

        :return: The filesystem paths for the directories from deepest or most specific
            to the top-level download client's ``downloadDir`` and it's siblings.
        """
        managed_dirs = []
        for servarr_download_client in self.servarrs.values():
            managed_dirs.append(servarr_download_client.download_dir)
            managed_dirs.append(servarr_download_client.seeding_dir)
        managed_dirs.append(self.download_dir)
        managed_dirs.append(self.seeding_dir)
        if self.incomplete_dir is not None:  # pragma: no cover
            managed_dirs.append(self.incomplete_dir)
        return managed_dirs

    @cached_property
    def items(self) -> list:
        """
        Request the download items from the client as needed and cache.

        :return: The ``prunerr.downloaditem.PrunerrDownloadItem()`` instances.
        """
        logger.debug(
            "Retrieving list of download items from download client: %s",
            self.config["url"],
        )
        items = [
            prunerr.downloaditem.PrunerrDownloadItem(
                self,
                torrent._client,
                torrent,
            )
            # TODO: Reduce memory consumption, narrow the list of fields requested for
            # all items.  Maybe also have separate sets of fields for operations done
            # on the whole list of items (e.g. filtering to find seeding items) and
            # operations on individual torrents (e.g. review).
            for torrent in self.client.get_torrents()
        ]

        # Record when the items were requested to identify filesystem changes that are
        # more current than our list of items:
        self.items_requested = datetime.datetime.now(datetime.timezone.utc)

        # Ensure that all Servarr instances are also up to date, clear cached items:
        for servarr in self.servarrs.values():
            vars(servarr).pop("items", None)

        return items

    def clear(self):
        """
        Reset derived attributes cached in this instance.
        """
        super().clear()
        self.servarrs.clear()
        for attr in ("config", "client"):
            vars(self).pop(attr, None)

    # Sub-commands

    def review(self) -> dict:
        """
        Apply configured review operations to all download items.

        :return: Map download item hash IDs to mappings describing the actions taken if
            any.
        """
        # TODO: Maybe handle multiple downloading items for the
        # same Servarr item such as when trying several to see which
        # ones actually have decent download speeds?
        results = {}
        # Need to make a copy in case review leads to deleting an item and modifying
        # `self.items`.
        download_dir = pathlib.Path(self.client.session.download_dir)
        for item in [
            item
            for item in self.items
            # Only review new items, IOW only those that haven't been imported yet:
            if download_dir in item.path.parents
            # Only review items once based on whether the log file has been written
            # to more recently than the configuration has been modified:
            and (
                not item.log_path.exists()
                or self.runner.config_stat.st_mtime > item.log_path.stat().st_mtime
            )
        ]:
            # Log messages specific to this download item to a dedicated log file:
            item.log_path.parent.mkdir(parents=True, exist_ok=True)
            item_handler = logging.FileHandler(item.log_path)
            item_handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
            item_results = None
            root_logger.addHandler(item_handler)
            try:
                item_results = item.review()
            except utils.RETRY_EXC_TYPES:
                logger.exception(
                    "Error reviewing item: %s",
                    item,
                )
            finally:
                root_logger.removeHandler(item_handler)
                item_handler.acquire()
                item_handler.flush()
                item_handler.close()

            if item_results:
                results[item.hashString] = item_results

        return results

    def re_add(self) -> list:
        """
        Remove and re-add all download items with nothing downloaded.

        :return: List all the items that were re-added to the download client.
        """
        # Transmission seems to verify items in the order of their indexes, in the order
        # they were added, so reverse the order to avoid clashing with items in the
        # process of verifying:
        re_add_results = []
        for item in reversed(self.items):
            # Skip items from the older full-list response first for speed:
            if not item.re_add_check(self.seeding_dir):
                continue  # pragma: no cover
            # Also get the latest item data in case it has finished verifying while
            # previous items were re-added:
            item.update()
            if not item.re_add_check(self.seeding_dir):  # pragma: no cover
                logger.debug(
                    "Not re-adding download item whose metadata changed: %r",
                    item,
                )
                continue
            re_add_results.append(item.re_add().name)
        return re_add_results

    # Other, non-sub-command methods

    def sort_free_space_items(self, items: collections.abc.Iterable) -> list:
        """
        Sort the given download items according to the indexer priority operations.

        :param items: The ``prunerr.downloaditem.PrunerrDownloadItem()`` instances.
        :return: The sorted ``items``.
        """
        return sorted(
            items,
            # remove lowest priority and highest ratio first
            key=lambda item: self.runner.config["operations"]["free-space"][
                "sort"
            ].render(item=item),
            reverse=True,
        )

    # Methods used by the `free-space` sub-command

    def delete_files(
        self,
        item: typing.Union[prunerr.downloaditem.PrunerrDownloadItem, pathlib.Path],
    ) -> int:
        """
        Delete all files and directories for the given path and stat or download item.

        First remove from the download client if given a download item.

        :param item: A filesystem path or a download item to be deleted.
        :return: The size of deleted files in bytes or B.
        """
        # Handle actual items recognized by the download client
        if isinstance(item, prunerr.downloaditem.PrunerrDownloadItem):
            size = item.disk_usage
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
            # Delete the actual files ourselves to workaround Transmission hanging when
            # deleting the data of large items: e.g. season packs.
            for item_file in item.files:
                # Remove each item file whether in the `download-dir` or the
                # `incomplete-dir`:
                self.delete_path(item_file.path)
            if item.log_path.exists():
                self.delete_path(item.log_path)

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

            self.delete_path(path)

        # Refresh the sessions data including free space.
        # TODO: Until we aggregate download client directories by `*.stat().st_dev`, we
        # can't know which of their sessions to update when we delete a path.  Maybe
        # implement?  Premature optimization?
        for download_client in self.runner.download_clients.values():
            download_client.client.get_session()

        return size

    def delete_path(self, path: pathlib.Path) -> pathlib.Path:
        """
        Delete this file or directory and empty parent directories.

        :param path: The filesystem path to a file to delete or a directory to
            recursively delete.
        :return: The filesystem paths for all parent directories that were also deleted.
        :raises ValueError: The given ``path`` is not valid to delete.
        """
        # The path is not in one of our managed directories, this should never happen:
        for managed_dir in self.managed_dirs:
            if managed_dir in path.parents:
                break
        else:
            raise ValueError(  # pragma: no cover
                "Refusing to delete a path in an un-managed directory",
            )

        # Delete the given path:
        if path.is_dir():
            shutil.rmtree(path, onerror=log_rmtree_error)  # pragma: no cover
        elif path.exists():
            path.unlink()
        else:
            # Under high download client load, the deletion from the client
            # sometimes seems to fail but Prunerr successfully deletes the data. On
            # the next `daemon` loop Prunerr will try to delete it from the client
            # again, which is correct, but then chokes on the missing files it
            # already deleted.
            logger.error(  # pragma: no cover
                "Path to be deleted doesn't exist: %s",
                path,
            )

        # Also remove the ancestor directories if they're not empty:
        removed_parents = []
        for relative_parent in path.relative_to(managed_dir).parents[:-1]:
            parent = managed_dir / relative_parent
            if next(parent.iterdir(), None) is not None:
                # Not empty, stop removing parents:
                break  # pragma: no cover
            parent.rmdir()
            removed_parents.append(parent)
        return removed_parents

    def try_delete_files(
        self,
        item: typing.Union[prunerr.downloaditem.PrunerrDownloadItem, pathlib.Path],
    ) -> int:
        """
        Attempt to delete a path or a download item, but tolerate and log failures.

        :param item: A `pathlib.Path()` filesystem path or a download item to be
            deleted.
        :return: The size of deleted files in bytes or B.
        :raises Exception: Deleting files raised an exception.
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

    def free_space_check(self) -> bool:
        """
        Determine if there's sufficient free disk space.

        :return: Whether or not free space is sufficient.
        """
        total_remaining_download = sum(
            item.leftUntilDone
            for item in self.items
            if item.status
            == prunerr.downloaditem.PrunerrDownloadItem.STATUS_DOWNLOADING
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
            # TODO: Clear the record of whether a notification was previously sent.
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

    def find_unregistered(self) -> list:  # noqa: V105
        """
        Filter already imported items that are no longer recognized by their tracker.

        For example, when a private tracker removes a duplicate/invalid/unauthorized
        item.

        :return: The ``prunerr.downloaditem.PrunerrDownloadItem()`` instances for
            unregistered download items.
        """
        # TODO: Mark as failed in Servarr?
        seeding_dirs = [servarr.seeding_dir for servarr in self.servarrs.values()]
        return self.sort_free_space_items(
            item
            for item in self.items
            if (
                (
                    item.status == item.STATUS_DOWNLOADING
                    # Give seeding items time to be imported by Servarr since they've
                    # already been fully downloaded.
                    or [
                        seeding_dir
                        for seeding_dir in seeding_dirs
                        if seeding_dir in item.path.parents
                    ]
                )
                and item.error == item.ERROR_TYPE_TRACKER_ERROR
                and self.UNREGISTERED_ERROR_RE.match(item.errorString.lower())
                is not None
            )
        )

    def find_seeding(self) -> list:  # noqa: V105
        """
        Filter items that have not yet been imported by Servarr, order by priority.

        :return: The ``prunerr.downloaditem.PrunerrDownloadItem()`` instances of seeding
            download items.
        """
        return self.sort_free_space_items(
            item
            for item in self.items
            # only those previously acted on by Servarr and moved
            if item.status == item.STATUS_SEEDING
            and self.seeding_dir in item.path.parents
            and self.runner.config["operations"]["free-space"]["include"].render(
                item=item,
            )
        )

    def verify_corrupt_items(self) -> typing.Optional[list]:
        """
        Verify and resume download items flagged as having corrupt data.

        :return: The ``prunerr.downloaditem.PrunerrDownloadItem()`` instances of the
            download items Prunerr started verifying.
        """
        corrupt_items = {
            item.hashString: item
            for item in self.items
            if item.hashString not in self.verifying_items
            and item.error == item.ERROR_TYPE_LOCAL
            and (
                item.ERROR_STR_CORRUPT in item.errorString.lower()
                or item.ERROR_STR_VERIFY in item.errorString.lower()
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

    def resume_verified_items(self) -> dict:
        """
        Resume downloading any previously corrupt items that have finished verifying.

        :return: Map download item hash IDs to the
            ``prunerr.downloaditem.PrunerrDownloadItem()`` instances of the download
            items that finished verifying.
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

    def add_torrent(
        self,
        download_url: str,
        **kwargs,
    ) -> prunerr.downloaditem.PrunerrDownloadItem:
        """
        Add a torrent to the download client and update instance state.

        :param download_url: The URL from which to download the torrent to add.
        :param kwargs: Additional arguments passed onto
            ``transmission_rpc.client.Client.add_torrent()``.
        :return: The added download item.
        """
        logger.info("Downloading torrent: %s", download_url)
        response = requests.get(download_url, timeout=5, stream=True)
        response.raise_for_status()
        added_torrent = prunerr.downloaditem.PrunerrDownloadItem(
            self,
            self.client,
            self.client.add_torrent(torrent=response.raw, **kwargs),
        )
        self.items.append(added_torrent)
        return added_torrent


class DownloadClientTimeout(Exception):
    """A download client operation took too long."""


def config_from_url(auth_url: str) -> dict:
    """
    Normalize download client URLs for the port and without the password.

    Used for matching with Servarr download clients.

    :param auth_url: The download client URL including authentication credentials.
    :return: The Prunerr download client configuration.
    """
    auth_url_split = urllib.parse.urlsplit(auth_url)
    url = utils.normalize_url(auth_url)
    return {"url": url, "password": auth_url_split.password}


def calc_free_space_margin(config: dict) -> int:
    """
    Calculate an appropriate margin of disk space to keep free.

    Used when deciding whether to delete download items and their files in the
    `free-space` sub-command based on the maximum download bandwidth/speed in Mbps and
    the amount of time in seconds at that rate for which download clients should be able
    to continue downloading without exhausting disk space.

    :param config: The Prunerr download client configuration.
    :return: The free space margin in bytes or B.
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
def log_rmtree_error(
    function: collections.abc.Callable,
    path: pathlib.Path,
    excinfo: tuple,
):
    """
    Inform the user on errors deleting item files but also proceed to delete the rest.

    Error handler for `shutil.rmtree`.

    :param function: See ``shutil.rmtree()`` in the Python standard library.
    :param path: See ``shutil.rmtree()`` in the Python standard library.
    :param excinfo: See ``shutil.rmtree()`` in the Python standard library.
    """
    logger.error(  # pragma: no cover
        "Error removing %r (%s)",
        path,
        ".".join((function.__module__, function.__name__)),
        exc_info=excinfo,
    )
