"""
Prunerr interaction with download clients.
"""

import os
import time
import copy
import pathlib
import shutil
import urllib.parse
import json
import pprint
import logging

import ciso8601
import transmission_rpc

import prunerr.utils
import prunerr.operations

logger = logging.getLogger(__name__)


def parallel_to(base_path, parallel_path, root_basename):
    """
    Return a path with a parallel relative root to the given full path.
    """
    base_path = pathlib.Path(base_path)
    common_path = pathlib.Path(os.path.commonpath((base_path.parent, parallel_path)))
    if common_path == pathlib.Path(os.sep):
        logger.warning(
            "The only common path between %r and %r is the filesystem root.  "
            "This is probably a sign of mis-configuration.",
            base_path.parent,
            parallel_path,
        )
    return (
        common_path
        / root_basename
        / pathlib.Path(parallel_path).relative_to(
            parallel_path.parents[-(len(base_path.parts))],
        )
    )


class PrunerrDownloadClient:
    """
    An individual, specific download client that Prunerr interacts with.
    """

    DATA_FILE_EXT = "-prunerr.json"
    # TODO: Make configurable?
    SEEDING_DIR_BASENAME = "seeding"

    client = None
    items = None

    def __init__(self, runner, config, servarr=None):
        """
        Capture a references to the runner and individual download client configuration.
        """
        self.runner = runner
        self.config = config
        self.min_free_space = calc_free_space_margin(runner.config)
        self.servarrs = {}
        if servarr is not None:
            self.servarrs[servarr.servarr.config["url"]] = servarr
        self.operations = prunerr.operations.PrunerrOperations(
            self,
            runner.config.get("indexers", {}),
        )

    def connect(self):
        """
        Connect to the download client's RPC client.
        """
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
        self.update()

        return self.client

    def update(self):
        """
        Update the list of download items from the download client.
        """
        logger.debug(
            "Retrieving list of download items from download client: %s",
            self.config["url"],
        )
        self.items = [
            PrunerrDownloadItem(
                self,
                torrent._client,  # pylint: disable=protected-access
                torrent,
            )
            for torrent in self.client.get_torrents()
        ]
        return self.items

    # Sub-commands

    def sync(self):
        """
        Synchronize the state of download client items with Servarr event history.
        """
        # TODO: Stop after first Servarr that matches?  Try data file and Servarr queue
        # match for each Servarr first.  IOW, avoid history search as much as possible.
        return {
            servarr_url: servarr_download_client.sync()
            for servarr_url, servarr_download_client in self.servarrs.items()
        }

    # Other, non-sub-command methods

    def get_item(self, download_id):
        """
        Get a download client item, tolerate missing items while logging the error.
        """
        if isinstance(download_id, str):
            download_id = download_id.lower()
        try:
            torrent = self.client.get_torrent(download_id)
            return prunerr.downloadclient.PrunerrDownloadItem(
                self,
                self.client,
                torrent,
            )
        except KeyError:
            # Can happen if the download client item has been manually deleted
            logger.error(
                "Could not find item in download client "
                "for Servarr imported event: %s",
                download_id,
            )
        return None

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

    def delete_files(self, item):
        """
        Delete all files and directories for the given path and stat or download item.

        First remove from the download client if given a download item.
        """
        # Handle actual items recognized by the download client
        if isinstance(item, PrunerrDownloadItem):
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
                        item.lookup_indexer(),
                        item.bandwidthPriority,
                        item.ratio,
                    )
                ),
            )
            self.client.remove_torrent([item.hashString])
            # Refresh the list of download items
            self.update()
            path = item.path

        # Handle filesystem paths not recognized by the download client
        else:
            path, stat = item
            size = stat.st_size
            logger.info(
                "Deleting %r: %0.2f %s + %0.2f %s",
                item,
                *(
                    transmission_rpc.utils.format_size(
                        self.client.session.download_dir_free_space,
                    )
                    + transmission_rpc.utils.format_size(size)
                ),
            )

        TODO  # Delete Prunerr files
        # Delete the actual files ourselves to workaround Transmission hanging when
        # deleting the data of large items: e.g. season packs.
        if path.is_dir():
            shutil.rmtree(path, onerror=log_rmtree_error)
        else:
            path.unlink()
        if next(path.parent.iterdir(), None) is None:
            # The directory containging the file is empty
            path.parent.rmdir()

        # Refresh the sessions data including free space
        self.client.get_session()
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
        seeding_dirs = [
            servarr.download_item_dirs["seedingDir"]
            for servarr in self.servarrs.values()
        ]
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
        seeding_dirs = [
            servarr.download_item_dirs["seedingDir"]
            for servarr in self.servarrs.values()
        ]
        return self.sort_items_by_tracker(
            item
            for item in self.items
            # only those previously synced and moved
            if item.status == "seeding"
            and [
                seeding_dir
                for seeding_dir in seeding_dirs
                if seeding_dir in item.path.parents
            ]
            # TODO: Optionally include imported items for Servarr configurations that
            # copy items instead of making hard-links, such as when the download client
            # isn't on the same host as the Servarr instance
            and self.operations.exec_indexer_operations(item)[0]
        )


class PrunerrDownloadItem(transmission_rpc.Torrent):
    """
    Enrich download item data from the download client API.
    """

    def __init__(self, download_client, client, torrent):
        """
        Reconstitute the native Python representation.
        """
        self.download_client = download_client
        super().__init__(
            client,
            {field_name: field.value for field_name, field in torrent._fields.items()},
        )

    @property
    def root_name(self):
        """
        Return the name of the first path element for all items in the download item.

        Needed because it's not always the same as the item's name.  If the download
        item has multiple files, assumes that all files are under the same top-level
        directory.
        """
        item_files = self.files()
        if item_files:
            return pathlib.Path(item_files[0].name).parts[0]
        return self.name

    @property
    def path(self):
        """
        Return the root path for all files in the download item.

        Needed because it's not always the same as the item's download directory plus
        the item's name.
        """
        return (pathlib.Path(self.download_dir) / self.root_name).resolve()

    @property
    def files_parent(self):
        """
        The path in which the download item's files are currently stored.

        This may be the `incomplete_dir` while the item is downloading.
        """
        download_dir = pathlib.Path(self.download_dir)
        if (
            self.download_client.client.session.incomplete_dir_enabled
            and not download_dir.is_dir()
        ):
            download_dir = pathlib.Path(
                self.download_client.client.session.incomplete_dir
            )
        return (download_dir / self.root_name).resolve()

    @property
    def age(self):
        """
        The total time since the item was added.
        """
        return time.time() - self._fields["addedDate"].value

    @property
    def seconds_since_done(self):
        """
        Number of seconds elapsed since the download item was completely downloaded.

        Best available estimation of total seeding time.
        """
        if self._fields["leftUntilDone"].value or self._fields["percentDone"].value < 1:
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
        ) / (done_date - self._fields["addedDate"].value)

    @property
    def size_imported(self):
        """
        The total size of item files that have been imported by Servarr.

        IOW, the sum of sizes of all item file that have more than one hard link.
        """
        return sum(
            stat.st_size for path, stat in self.list_files_stats() if stat.st_nlink >= 1
        )

    @property
    def size_imported_proportion(self):
        """
        The proportion of total size of files that have been imported by Servarr.
        """
        total = 0
        imported = 0
        for _, stat in self.list_files_stats():
            total += stat.st_size
            if stat.st_nlink >= 1:
                imported += stat.st_size
        if total:
            return imported / total
        return 0

    @property
    def prunerr_data_path(self):
        """
        Determine the correct sibling path for the Prunerr data file.
        """
        # TODO: Cache?
        if self.files_parent.is_file():
            return self.files_parent.with_suffix(self.download_client.DATA_FILE_EXT)
        return self.files_parent.with_name(
            f"{self.files_parent.name}{self.download_client.DATA_FILE_EXT}"
        )

    @property
    def prunerr_data(self):
        """
        Load the prunerr data file.
        """
        if "prunerr_data" in vars(self):
            return vars(self)["prunerr_data"]

        # Move the data file if the download item files have been moved since the last
        # `sync`.
        if not self.prunerr_data_path.exists():
            download_dir = pathlib.Path(self.download_dir)
            data_paths = (
                parallel_to(
                    self.download_client.client.session.download_dir,
                    download_dir,
                    self.download_client.SEEDING_DIR_BASENAME,
                )
                / self.prunerr_data_path.name,
                download_dir / self.prunerr_data_path.name,
            )
            if self.download_client.client.session.incomplete_dir_enabled:
                data_paths += (
                    pathlib.Path(self.download_client.client.session.incomplete_dir)
                    / self.prunerr_data_path.name,
                )
            src_data_path = max(
                (data_path for data_path in data_paths if data_path.exists()),
                key=lambda data_path: data_path.stat().st_mtime,
                default=None,
            )
            if src_data_path is not None:
                logger.debug(
                    "Moving newest Prunerr data file: %r -> %r",
                    str(src_data_path),
                    str(self.prunerr_data_path),
                )
                src_data_path.rename(self.prunerr_data_path)

        # Load the Prunerr data file
        download_data = dict(path=self.prunerr_data_path, history={})
        if (
            not self.download_client.runner.replay
            and self.prunerr_data_path.exists()
            and self.prunerr_data_path.stat().st_size
        ):
            with self.prunerr_data_path.open() as data_opened:
                try:
                    download_data = json.load(data_opened)
                except json.JSONDecodeError:
                    logger.exception(
                        "Failed to deserialize JSON file: %s",
                        self.prunerr_data_path,
                    )
            download_data["path"] = self.prunerr_data_path
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
                ciso8601.parse_datetime(
                    history_date
                ): prunerr.utils.deserialize_history(history_record)
                for history_date, history_record in download_data["history"].items()
            }

        # Cache the deserialized and normalized data
        vars(self)["prunerr_data"] = download_data
        return download_data

    def serialize_download_data(self, download_history=None):
        """
        Serialize an item's Prunerr data and write to the Prunerr data file.
        """
        # TODO: Still necessary after rewrite/cleanup?
        download_data = copy.deepcopy(self.prunerr_data)
        # Convert loaded JSON to native types where possible
        if download_history is not None:
            download_history = {
                history_date.strftime(
                    prunerr.utils.SERVARR_DATETIME_FORMAT
                ): prunerr.utils.serialize_history(copy.deepcopy(history_record))
                for history_date, history_record in download_history.items()
            }
        download_data["history"] = download_history
        if "latestImportedDate" in download_data:
            download_data["latestImportedDate"] = download_data[
                "latestImportedDate"
            ].strftime(prunerr.utils.SERVARR_DATETIME_FORMAT)
        if "path" in download_data:
            download_data["path"] = str(download_data["path"])
        existing_deserialized = ""
        if self.prunerr_data_path.exists():
            with self.prunerr_data_path.open("r") as data_read:
                existing_deserialized = data_read.read()
        with self.prunerr_data_path.open("w") as data_opened:
            logger.debug(
                "Writing Prunerr download item data: %s",
                self.prunerr_data_path,
            )
            try:
                json.dump(download_data, data_opened, indent=2)
            except DownloadClientTODOException:
                logger.exception(
                    "Failed to serialize to JSON file, %r:\n%s",
                    str(self.prunerr_data_path),
                    pprint.pformat(download_data),
                )
                data_opened.seek(0)
                data_opened.write(existing_deserialized)

    def move(self, location):
        """
        Move the given download item relative to its old path.
        """
        src_path = pathlib.Path(self.download_dir)
        data_path = self.prunerr_data_path
        logger.info("Moving %r: %r -> %r", self, self.download_dir, location)
        self.move_data(location)
        try:
            self.move_timeout()
        except DownloadClientTimeout as exc:
            logger.error("Moving download item timed out, pausing: %s", exc)
            self.stop()
        finally:
            self.update()

        # Move any files managed by Prunerr that belong to this download item.
        # Explicit is better than implicit, specific e.g.: if a user has manually
        # extracted an archive in the old import location we want the orphan logic to
        # find it after Servarr has upgraded it
        prunerr_files = set()
        if self.path.is_file():
            prunerr_files.update(
                src_path.parent.glob(
                    src_path.with_name(f"{src_path.name}-servarr-imported.ln"),
                )
            )
        else:
            prunerr_files.update(src_path.glob("*-servarr-imported.ln"))
            prunerr_files.update(src_path.glob("**/*-servarr-imported.ln"))
        if data_path.exists():
            prunerr_files.add(data_path)
        for prunerr_file in prunerr_files:
            prunerr_file.rename(location / prunerr_file.relative_to(src_path))
            if prunerr_file.parent != pathlib.Path(src_path) and not list(
                prunerr_file.parent.iterdir()
            ):
                prunerr_file.parent.rmdir()  # empty dir

        return location

    def move_timeout(self, move_timeout=5 * 60):
        """
        Block until an item's files are no longer in the old location.

        Useful for both moving and deleting.
        """
        # Wait until the files are finished moving
        start = time.time()
        while list(self.list_files()):
            if time.time() - start > move_timeout:
                raise DownloadClientTimeout(f"Timed out waiting for {self} to move")
            time.sleep(1)

    def list_files(self, selected=True):
        """
        Iterate over all download item file paths that exist.

        Optionally filter the list by those that are selected in the download client.
        """
        files = self.files()
        if not files:
            raise ValueError(f"No files found in {self!r}")

        return (
            self.path.parent / file_.name
            for file_ in files
            if (not selected or file_.selected)
            and os.path.exists(os.path.join(self.download_dir, file_.name))
        )

    def list_files_stats(self):
        """
        Yield the path and stat for all item files.

        Useful to avoid redundant `stat` syscalls.
        """
        for item_file in self.list_files(selected=False):
            yield item_file, item_file.stat()

    def match_indexer_urls(self):
        """
        Return the indexer name if the download item matches a configured tracker URL.
        """
        for possible_name, possible_urls in (
            self.download_client.runner.config.get(
                "indexers",
                {},
            )
            .get("urls", {})
            .items()
        ):
            for tracker in self.trackers:
                for action in ("announce", "scrape"):
                    tracker_url = tracker[action]
                    for indexer_url in possible_urls:
                        if tracker_url.startswith(indexer_url):
                            return possible_name
        return None

    def lookup_indexer(self):
        """
        Lookup the indexer for this item and cache.
        """
        if "indexer" in self.prunerr_data:
            return self.prunerr_data["indexer"]

        indexer_name = None
        # Try to find an indexer name from the items Servarr history
        for servarr_download_client in self.download_client.servarrs.values():
            if servarr_download_client.get_item_servarr_dir(self):
                # Also collects the indexer name if possible
                servarr_download_client.get_item_dir_id(self)
                indexer_name = self.prunerr_data.get("indexer")
                if indexer_name is not None:
                    break
        else:
            logger.debug(
                "No Servarr history found for download item: %r",
                self,
            )
        # The indexer has been added to the Prunerr data, persist it to the Prunerr data
        # file.
        # TODO: This is redundant for any sub-command that runs `sync` which will write
        # the Prunerr data file at the end.
        self.serialize_download_data(self.prunerr_data["history"])

        # Match by indexer URLs when no indexer name is available
        if not indexer_name:
            indexer_name = self.match_indexer_urls()

        return indexer_name


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
