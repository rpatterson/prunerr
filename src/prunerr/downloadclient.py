"""
Prunerr interaction with download clients.
"""

import os
import time
import copy
import pathlib
import urllib.parse
import json
import pprint
import logging

import ciso8601
import transmission_rpc

import prunerr.utils

logger = logging.getLogger(__name__)


def parallel_to(base_dir, parallel_path, root_basename):
    """
    Return a path with a parallel relative root to the given full path.
    """
    base_dir = pathlib.Path(base_dir)
    assert base_dir.name != root_basename, (
        "Parallel root basename same as the relative root: "
        f"{base_dir!r} -> {parallel_path!r}"
    )
    return (
        base_dir.parent
        / root_basename
        / pathlib.Path(parallel_path).relative_to(base_dir)
    )


class PrunerrDownloadClient:
    """
    An individual, specific download client that Prunerr interacts with.
    """

    DATA_FILE_EXT = "-prunerr.json"
    # TODO: Make configurable?
    SEEDING_DIR_BASENAME = "seeding"

    client = None
    download_items = None

    def __init__(self, runner, config, servarr=None):
        """
        Capture a references to the runner and individual download client configuration.
        """
        self.runner = runner
        self.config = config
        self.servarrs = {}
        if servarr is not None:
            self.servarrs[servarr.servarr.config["url"]] = servarr

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
        self.download_items = [
            PrunerrDownloadItem(
                self,
                torrent._client,  # pylint: disable=protected-access
                torrent,
            )
            for torrent in self.client.get_torrents()
        ]
        return self.download_items

    def sync(self):
        """
        Synchronize the state of download client items with Servarr event history.
        """
        # TODO: Stop after first Servarr that matches?  Try data file and Servarr queue
        # match for each Servarr first.  IOW, avoid history search as much as possible.
        return {
            servarr_url: servarr_download_client.sync(self.download_items)
            for servarr_url, servarr_download_client in self.servarrs.items()
        }


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

        Needed because it's not always the same as the item's name.  If download_item
        has multiple files, assumes that all files are under the same top-level
        directory.
        """
        item_files = self.files()
        if item_files:
            return pathlib.Path(item_files[0].name).parts[0]
        return self.name

    @property
    def path(self):
        """
        Return the root path for all items in the download client item.

        Needed because it's not always the same as the item's download directory plus
        the item's name.
        """
        return (pathlib.Path(self.download_dir) / self.root_name).resolve()

    @property
    def files_parent(self):
        """
        The path in which the items files are currently stored.

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
        Number of seconds elapsed since the download_item was completely downloaded.

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

    def move(self, old_path, new_path):
        """
        Move the given download item relative to its old path.
        """
        download_dir = self.downloadDir
        src_path = self.path
        data_path = self.prunerr_data_path
        if pathlib.Path(old_path) not in src_path.parents:
            raise ValueError(
                f"Download item {self!r} not in expected location: "
                f"{str(old_path)!r} vs {download_dir!r}"
            )
        split = splitpath(os.path.relpath(download_dir, os.path.dirname(old_path)))[1:]
        subpath = split and os.path.join(split[0], *split[1:]) or ""
        location = os.path.join(new_path, subpath)
        logger.info("Moving %r: %r -> %r", self, self.download_dir, location)
        self.move_data(location)
        try:
            self.move_timeout(download_dir)
        except DownloadClientTimeout as exc:
            logger.error("Moving download item timed out, pausing: %s", exc)
            self.stop()
        finally:
            self.update()

        # Move any non-download_item files managed by Prunerr
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
            prunerr_file.rename(
                pathlib.Path(new_path) / prunerr_file.relative_to(old_path),
            )
            if prunerr_file.parent != pathlib.Path(old_path) and not list(
                prunerr_file.parent.iterdir()
            ):
                prunerr_file.parent.rmdir()  # empty dir

        return location

    def move_timeout(self, download_dir, move_timeout=5 * 60):
        """
        Block until a torrents files are no longer in the old location.

        Useful for both moving and deleting.
        """
        # Wait until the files are finished moving
        start = time.time()
        while list(self.list_files(download_dir)):
            if time.time() - start > move_timeout:
                raise DownloadClientTimeout(
                    f"Timed out waiting for {self} to move "
                    f"from {download_dir!r}".format(**locals())
                )
            time.sleep(1)

    def list_files(self, download_dir=None):
        """
        Iterate over all download item selected file paths that exist.
        """
        if download_dir is None:
            download_dir = self.downloadDir

        files = self.files()
        assert files, "Must be able to find download item files"

        return (
            file_.name
            for file_ in files
            if file_.selected and os.path.exists(os.path.join(download_dir, file_.name))
        )

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


class DownloadClientTimeout(Exception):
    """A download client operation took too long."""


class DownloadClientTODOException(Exception):
    """
    Placeholder exception until we can determine the correct, narrow list of exceptions.
    """
