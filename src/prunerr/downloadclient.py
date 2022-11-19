"""
Prunerr interaction with download clients.
"""

import os
import pathlib
import shutil
import urllib.parse
import logging

import transmission_rpc

import prunerr.downloaditem
import prunerr.operations

logger = logging.getLogger(__name__)


class PrunerrDownloadClient:
    """
    An individual, specific download client that Prunerr interacts with.
    """

    DATA_FILE_SUFFIX = "-prunerr.json"
    SERVARR_IMPORTED_LINK_SUFFIX = "-servarr-imported.ln"
    FILE_SUFFIXES = {DATA_FILE_SUFFIX, SERVARR_IMPORTED_LINK_SUFFIX}
    # TODO: Make configurable?
    SEEDING_DIR_BASENAME = "seeding"

    config = None
    client = None
    items = None
    operations = None
    min_free_space = None

    def __init__(self, runner):
        """
        Capture a references to the runner and individual download client configuration.
        """
        self.runner = runner
        self.servarrs = {}

    def __repr__(self):
        """
        Readable, informative, and specific representation to ease debugging.
        """
        return f"<{type(self).__name__} at {self.config['url']!r}>"

    def update(self, config=None):
        """
        Update configuration, connect the RPC client, and update the list of items.
        """
        if config is not None:
            self.config = config
        if self.config is None:
            raise ValueError("No download client configuration provided")

        # Configuration specific to Prunerr, IOW not taken from the download client
        self.min_free_space = calc_free_space_margin(self.runner.config)
        self.operations = prunerr.operations.PrunerrOperations(
            self,
            self.runner.config.get("indexers", {}),
        )

        # Connect to the download client's RPC API, also retrieves session data
        split_url = urllib.parse.urlsplit(self.config["url"])
        port = split_url.port
        if not port:
            if split_url.scheme == "http":
                port = 80
            elif split_url.scheme == "https":
                port = 443
            else:
                raise ValueError(f"Could not guess port from URL: {self.config['url']}")
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
            password=split_url.password,
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
        for item in list(self.items):
            if pathlib.Path(self.client.session.download_dir) not in item.path.parents:
                # Support exempting items from review, put them in a different location.
                # Only review items in the client's default download directory.
                logger.debug(
                    "Ignoring item not in default download dir: %r",
                    item,
                )
                continue
            try:
                results[item] = item.review(servarr_queue)
            except DownloadClientTODOException:
                logger.exception(
                    "Un-handled exception reviewing item: %r",
                    item,
                )
                if "DEBUG" in os.environ:
                    raise
                continue
        return results

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
        """
        # Handle actual items recognized by the download client
        if isinstance(item, prunerr.downloaditem.PrunerrDownloadItem):
            size = item.totalSize
            self.operations.exec_indexer_operations(item)
            logger.info(
                "Deleting %r, "
                "%0.2f %s + %0.2f %s: indexer=%s, priority=%s, ratio=%0.2f",
                item,
                *(
                    transmission_rpc.utils.format_size(
                        self.client.session.download_dir_free_space,
                    )
                    + transmission_rpc.utils.format_size(size)
                    + (
                        item.match_indexer_urls(),
                        item.bandwidthPriority,
                        item.ratio,
                    )
                ),
            )
            self.client.remove_torrent([item.hashString])
            self.items.remove(item)
            path = item.files_parent

        # Handle filesystem paths not recognized by the download client
        else:
            path, stat = item
            size = stat.st_size
            logger.info(
                "Deleting %r: %0.2f %s + %0.2f %s",
                str(path),
                *(
                    transmission_rpc.utils.format_size(
                        self.client.session.download_dir_free_space,
                    )
                    + transmission_rpc.utils.format_size(size)
                ),
            )

        # Delete the actual files ourselves to workaround Transmission hanging when
        # deleting the data of large items: e.g. season packs.
        stem = path.stem if path.is_file() else path.name
        if path.is_dir():
            shutil.rmtree(path, onerror=log_rmtree_error)
        else:
            path.unlink()
        if next(path.parent.iterdir(), None) is None:
            # The directory containging the file is empty
            path.parent.rmdir()
        # Delete any files managed by Prunerr.
        for suffix in self.FILE_SUFFIXES:
            path.with_name(f"{stem}{suffix}").unlink(missing_ok=True)

        # Refresh the sessions data including free space.
        # TODO: Until we aggregate download client directories by `*.stat().st_dev`, we
        # can't know which of their sessions to update when we delete a path.  Maybe
        # implement?  Premature optimization?
        for download_client in self.runner.download_clients.values():
            download_client.client.get_session()

        return size

    def free_space_maybe_resume(self):
        """
        Determine if there's sufficient free disk space, resume downloading if paused.
        """
        total_remaining_download = sum(
            item.leftUntilDone for item in self.items if item.status == "downloading"
        )
        if total_remaining_download > self.client.session.download_dir_free_space:
            logger.debug(
                "Total size of remaining downloads is greater than the available free "
                "space: %0.2f %s > %0.2f %s",
                *(
                    transmission_rpc.utils.format_size(total_remaining_download)
                    + transmission_rpc.utils.format_size(
                        self.client.session.download_dir_free_space
                    )
                ),
            )
        if self.client.session.download_dir_free_space >= self.min_free_space:
            logger.debug(
                "Sufficient free space to continue downloading: %0.2f %s >= %0.2f %s",
                *(
                    transmission_rpc.utils.format_size(
                        self.client.session.download_dir_free_space,
                    )
                    + transmission_rpc.utils.format_size(
                        self.min_free_space,
                    )
                ),
            )
            self.resume_downloading(self.client.session)
            return True
        return False

    def resume_downloading(self, session):
        """
        Resume downloading if it's been stopped.
        """
        speed_limit_down = self.runner.config["download-clients"][
            "max-download-bandwidth"
        ]
        if session.speed_limit_down_enabled and (
            not speed_limit_down or speed_limit_down != session.speed_limit_down
        ):
            if (
                self.runner.config["download-clients"].get(
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

    def find_unregistered(self):
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
                and "unregistered item" in item.errorString.lower()
            )
        )

    def find_seeding(self):
        """
        Filter items that have not yet been imported by Servarr, order by priority.
        """
        return self.sort_items_by_tracker(
            item
            for item in self.items
            # only those previously acted on by Servarr and moved
            if item.status == "seeding"
            and pathlib.Path(self.client.session.download_dir).parent
            / self.SEEDING_DIR_BASENAME
            in item.path.parents
            and self.operations.exec_indexer_operations(item)[0]
        )


class DownloadClientTimeout(Exception):
    """A download client operation took too long."""


class DownloadClientTODOException(Exception):
    """
    Placeholder exception until we can determine the correct, narrow list of exceptions.
    """


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
            config["download-clients"]["max-download-bandwidth"]
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
            config["download-clients"].get("min-download-time-margin", 3600)
        )
    )


def log_rmtree_error(function, path, excinfo):
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
