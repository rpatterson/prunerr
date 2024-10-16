# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT


"""
Prunerr interaction with download clients.
"""

import typing
import collections
import datetime
import urllib.parse
import logging

import requests
import transmission_rpc

import prunerr.downloaditem
import prunerr.operations
from . import utils
from .utils import pathlib
from .utils import cached_property

logger = logging.getLogger(__name__)


class DownloadClientTimeout(Exception):
    """A download client operation took too long."""


class PrunerrDownloadClient(  # pylint: disable=too-many-instance-attributes
    utils.PrunerrComponent
):
    """
    An individual, specific download client that Prunerr interacts with.
    """

    TRANSMISSION_PATH = "/transmission/"
    # TODO: Make configurable?
    SEEDING_DIR_BASENAME = "seeding"
    TIMEOUT_EXCEPTION = DownloadClientTimeout

    client: transmission_rpc.client.Client
    session: dict
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
        # Support comparing changes since the last `$ prunerr daemon` loop:
        previous_session = vars(self).get("session", {})
        previous_session.pop("previous", None)
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
            # Workaround `transmission_rpc`'s special case logic:
            path=(
                split_url.path
                if split_url.path == self.TRANSMISSION_PATH
                else f"{split_url.path}/rpc"
            ),
            username=split_url.username,
            password=self.config["password"],
            timeout=self.config.get("timeout", example_config["timeout"]),
        )
        # Unfortunately, `transmission_rpc` now raises a `DeprecationWarning` when
        # trying to access the session settings after the initial connection and the
        # only way it provides is to send another, redundant request. Circumvent the
        # deprecation warning:
        self.session = vars(self.client)["_Client__raw_session"]
        self.session["previous"] = previous_session
        self.download_dir = pathlib.Path(self.session["download-dir"])
        self.seeding_dir = self.download_dir.with_name(self.SEEDING_DIR_BASENAME)
        if self.session["incomplete-dir-enabled"]:  # pragma: no cover
            self.incomplete_dir = pathlib.Path(
                self.session["incomplete-dir"],
            )

        # Update any Servarr references or data that depends on the download client
        # session data
        for download_dir, servarr_download_client in config.get("servarrs", {}).items():
            self.servarrs[download_dir] = servarr_download_client
            servarr_download_client.update_download_client(self)

    @cached_property
    def items(self) -> list:
        """
        Request the download items from the client as needed and cache.

        :return: The ``prunerr.downloaditem.PrunerrDownloadItem()`` instances.
        """
        logger.debug(
            "Retrieving list of download items from: %r",
            self,
        )
        items = [
            prunerr.downloaditem.PrunerrDownloadItem(
                self,
                torrent,
            )
            # TODO: Reduce memory consumption, CPU usage, and run-time by narrowing the
            # list of fields requested for all items.
            for torrent in self.client.get_torrents()
        ]

        # Record when the items were requested to identify filesystem changes that are
        # more current than our list of items:
        self.items_requested = datetime.datetime.now(datetime.timezone.utc)

        # Ensure that all Servarr instances are also up to date, clear cached items:
        for servarr in self.servarrs.values():
            vars(servarr).pop("items", None)

        return items

    @cached_property
    def item_files(self) -> dict:
        """
        Collate this download client's item files by each items relative file paths.

        :return: Map file relative paths to the download item hash IDs to the files.
        """
        item_files: dict = {}
        for item in self.items:
            for item_file in item.files:
                item_files.setdefault(item_file.relative, {})[
                    item.hash_string
                ] = item_file
        return item_files

    @cached_property
    def queued_items(self) -> list:
        """
        Filter items that have not yet been acted on by Servarr or Prunerr.

        :return: The download items.
        """
        # Avoid attribute and item lookup in the inner loop:
        download_dir = self.download_dir
        config_mtime = self.runner.config_stat.st_mtime

        queued_items = []
        for item in self.items:
            if (
                # Only new items, IOW only those that haven't been imported yet:
                (
                    download_dir in item.download_dir.parents
                    or download_dir == item.download_dir
                )
                # Only items once based on whether the log file has been written to more
                # recently than the configuration has been modified:
                and (
                    not item.log_path.exists()
                    or config_mtime > item.log_path.stat().st_mtime
                )
            ):
                queued_items.append(item)

        return queued_items

    def clear(self):
        """
        Reset derived attributes cached in this instance.
        """
        super().clear()
        self.servarrs.clear()
        for attr in ("config", "client"):
            vars(self).pop(attr, None)

    # Sub-commands

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

    # Methods to list the download items in each life-cycle stage:

    def filter_queued(self) -> list:  # noqa: V105
        """
        Filter items that have not yet been acted on by Servarr or Prunerr.

        :return: The download items.
        """
        return self.queued_items

    def filter_upgraded(self) -> collections.abc.Generator:  # noqa: V105
        """
        Filter queued items that will upgrade currently imported releases.

        :return: The ``prunerr.downloaditem.PrunerrDownloadItem()`` instances.
        """
        upgraded_releases: dict = {}
        for item in self.queued_items:
            if item.release is None:  # pragma: no cover
                logger.debug(
                    "No ``upgraded`` stage items for items not in Servarr queue: %r",
                    item,
                )
                continue
            for imported_release in item.release.filter_upgraded():
                upgraded_releases.setdefault(
                    imported_release.hash_string,
                    imported_release,
                )
        yield from upgraded_releases.values()

    def filter_seeding(self) -> collections.abc.Generator:
        """
        Filter items that have been acted on by Servarr.

        :return: The ``prunerr.downloaditem.PrunerrDownloadItem()`` instances.
        """
        for servarr_download_client in self.servarrs.values():
            yield from servarr_download_client.filter_seeding()

    def filter_free_space(self) -> collections.abc.Generator:  # noqa: V105
        """
        Filter seeding items that have been imported by Servarr and moved.

        :return: The ``prunerr.downloaditem.PrunerrDownloadItem()`` instances.
        """
        total_remaining_download = sum(
            item.fields["leftUntilDone"]
            for item in self.items
            if item.status
            == prunerr.downloaditem.PrunerrDownloadItem.STATUS_DOWNLOADING
        )
        if total_remaining_download > self.session["download-dir-free-space"]:
            logger.debug(
                "Total size of remaining downloads is greater than the available free"
                " space: %(remaining)s - %(free)s = %(deficit)s",
                {
                    "remaining": utils.format_size(
                        total_remaining_download,
                    ),
                    "free": utils.format_size(self.session["download-dir-free-space"]),
                    "deficit": utils.format_size(
                        total_remaining_download
                        - self.session["download-dir-free-space"]
                    ),
                },
            )
        if self.free_space_check():
            logger.debug(
                "Sufficient free space to continue downloading: "
                "%(free)s - %(minimum)s = %(surplus)s",
                {
                    "free": utils.format_size(self.session["download-dir-free-space"]),
                    "minimum": utils.format_size(
                        self.config["min-free-space"],
                    ),
                    "surplus": utils.format_size(
                        self.session["download-dir-free-space"]
                        - self.config["min-free-space"],
                    ),
                },
            )
        else:
            logger.debug(
                "Insufficient free space to continue downloading: "
                "%(minimum)s - %(free)s = %(deficit)s",
                {
                    "minimum": utils.format_size(
                        self.config["min-free-space"],
                    ),
                    "free": utils.format_size(self.session["download-dir-free-space"]),
                    "deficit": utils.format_size(
                        self.config["min-free-space"]
                        - self.session["download-dir-free-space"],
                    ),
                },
            )

        # Avoid attribute and item lookup in the inner loop:
        seeding_dir = self.seeding_dir

        # The filtering inherent to this life-cycle stage:
        for item in self.items:
            if item.status == item.STATUS_SEEDING and (
                seeding_dir in item.download_dir.parents
                or seeding_dir == item.download_dir
            ):
                yield item

    def filter_all(self) -> collections.abc.Generator:  # noqa: V105
        """
        Filter download items excluding those Servarr has yet to act on.

        :return: The ``prunerr.downloaditem.PrunerrDownloadItem()`` instances.
        """
        # Avoid attribute and item lookup in the inner loop:
        seeding_dir = self.seeding_dir

        for item in self.items:
            if item.status == item.STATUS_DOWNLOADING or (
                seeding_dir in item.download_dir.parents
                or seeding_dir == item.download_dir
            ):
                yield item
            else:
                pass  # pragma: no cover

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
        imported_files = [
            item_file
            for item_file in item.files
            if not item_file.is_servarr_extra
            and item_file.path.exists()
            and item_file.stat.st_nlink > 1
        ]
        unimported_files = [
            item_file
            for item_file in item.files
            if not item_file.path.exists() or item_file.stat.st_nlink == 1
        ]

        if imported_files and unimported_files:
            size = sum(item_file.disk_usage for item_file in unimported_files)
            logger.debug(
                "Deleting un-imported %(item)r files + %(size)s:"
                "\n  %(unimported_files)s",
                {
                    "item": item,
                    "size": utils.format_size(size),
                    "unimported_files": "\n  ".join(
                        repr(unimported_file) for unimported_file in unimported_files
                    ),
                },
            )
            item.download_client.client.change_torrent(
                [item.hash_string],
                files_unwanted=[
                    unimported_file.id for unimported_file in unimported_files
                ],
                # When freeing disk space it's important not to get hung up waiting for
                # a heavily loaded client. Be very defensive and proceed directly to
                # deleting the data:
                timeout=transmission_rpc.constants.DEFAULT_TIMEOUT,
            )

        else:
            if imported_files:
                logger.warning(  # pragma: no cover
                    "Deleting %(item)r with imported files:\n %(imported_files)s",
                    {
                        "item": item,
                        "imported_files": "\n  ".join(
                            str(imported_file.path) for imported_file in imported_files
                        ),
                    },
                )
            size = item.disk_usage
            logger.debug("Deleting %(item)r", {"item": item})
            self.client.remove_torrent(
                [item.hash_string],
                # When freeing disk space it's important not to get hung up waiting for
                # a heavily loaded client. Be very defensive and proceed directly to
                # deleting the data:
                timeout=transmission_rpc.constants.DEFAULT_TIMEOUT,
            )
            self.items.remove(item)

        # Delete the actual files ourselves to workaround Transmission hanging when
        # deleting the data of large items: e.g. season packs:
        for item_file in unimported_files:
            # Don't try to delete files for which nothing has been downloaded and
            # thus the file was never created:
            if item_file.completed or item_file.path.exists():
                # Remove each item file whether in the `download-dir` or the
                # `incomplete-dir`:
                self.runner.delete_path(item_file.path)
            else:
                pass  # pragma: no cover
        if not imported_files and item.log_path.exists():  # pragma: no cover
            self.runner.delete_path(item.log_path)

        # Refresh the sessions data including free space.
        # TODO: Until we aggregate download client directories by `*.stat().st_dev`, we
        # can't know which of their sessions to update when we delete a path.  Maybe
        # implement?  Premature optimization?
        for download_client in self.runner.download_clients.values():
            download_client.client.get_session()

        return size

    def free_space_check(  # noqa: V105
        self,
        session: typing.Optional[dict] = None,
    ) -> bool:
        """
        Determine if there's sufficient free disk space.

        :param session: The Transmission RPC session data.
        :return: Whether or not free space is sufficient.
        """
        if session is None:
            session = self.session
        if session["download-dir-free-space"] >= self.config["min-free-space"]:
            return True
        return False

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
            self.client.add_torrent(torrent=response.raw, **kwargs),
        )
        added_torrent.update()
        self.items.append(added_torrent)
        return added_torrent


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
