# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT


"""
Prunerr interaction with download clients.
"""

import os
import typing
import time
import urllib.parse
import json
import subprocess  # nosec, pragmatic choice for performance
import logging

import transmission_rpc

from . import utils
from .utils import pathlib
from .utils import cached_property

if typing.TYPE_CHECKING:  # pragma: no cover
    import prunerr.servarr.release

logger = logging.getLogger(__name__)


class PrunerrDownloadItem(
    utils.PrunerrComponent,
    transmission_rpc.Torrent,
):  # pylint: disable=too-many-public-methods
    """
    Enrich download item data from the download client API.
    """

    FIELD_HASH = "hashString"
    FIELD_DOWNLOAD_DIR = "downloadDir"
    STATUS_DOWNLOADING = "downloading"
    STATUS_SEEDING = "seeding"
    STATUS_SEEDING_INT = 6
    STATUS_CHECKING = "checking"
    ERROR_TYPE_TRACKER_ERROR = 2
    ERROR_TYPE_LOCAL = 3
    ERROR_STR_CORRUPT = "corrput"
    ERROR_STR_VERIFY = "verif"

    def __init__(self, download_client, client, torrent):
        """
        Reconstitute the native Python representation.
        """
        self.download_client = download_client
        super().__init__(
            client,
            {field_name: field.value for field_name, field in torrent._fields.items()},
        )
        self.files = [
            PrunerrDownloadItemFile(self, rpc_file) for rpc_file in super().files()
        ]

    @property
    def details(self) -> dict:
        """
        Assemble all available useful information.

        :return: Map descriptive names to useful values.
        """
        details = {}
        if (name := self._get_name_string()) is not None:
            details["name"] = name
        elif self.FIELD_HASH in self._fields:  # pragma: no cover
            details["hash"] = self._fields[self.FIELD_HASH].value
        else:  # pragma: no cover
            details["id"] = self._fields["id"].value
        details["indexer"] = self.match_indexer_urls()
        details["size"] = self.disk_usage
        imported_portion = round(
            (
                sum(
                    item_file.size
                    for item_file in self.files
                    if item_file.selected and item_file.is_imported
                )
                / self._fields["sizeWhenDone"].value
            )
            * 100
        )
        details["imported"] = f"{imported_portion}%"
        return details

    def update(self):
        """
        Update cached values when this download item is updated.
        """
        super().update()
        super(utils.PrunerrComponent, self).update()
        self.clear()

    def clear(self):
        """
        Reset derived attributes cached in this instance.
        """
        super().clear()
        for item_file in self.files:
            item_file.clear()

    @cached_property
    def download_dir(self) -> pathlib.Path:
        """
        Assemble the Transmission `download-dir` path.

        :return: The assembled path.
        """
        return pathlib.Path(super().download_dir).resolve()

    @cached_property
    def root_name(self) -> str:
        """
        Determine the name of the first path element for all items in the download item.

        Needed because it's not always the same as the item's name.  If the download
        item has multiple files, assumes that all files are under the same top-level
        directory.

        :return: The resulting basename.
        """
        file_roots = list(
            {item_file.relative.parts[0]: None for item_file in self.files}
        )
        if file_roots:
            if len(set(file_roots)) > 1:
                logger.error(
                    "Files in %r have multiple roots, using: %s",
                    self.name,
                    file_roots[0],
                    extra={
                        "runner": self.download_client.runner,
                        "download_hash": self.hashString,
                    },
                )
            return file_roots[0]
        return self.name

    @cached_property
    def path(self) -> pathlib.Path:
        """
        Assemble the root path for all files in the download item.

        See ``self.root_name`` for more details.

        :return: The resulting path object.
        """
        return self.download_dir / self.root_name

    @cached_property
    def parents(self) -> list:
        """
        Determine the directories that may contain item files.

        Include the `incomplete-dir` if enabled.

        :return: The candidate path objects in order of precedence.
        """
        parents = [self.download_dir]
        if (
            self.download_client.incomplete_dir is not None
            and self.download_client.incomplete_dir.exists()
        ):
            parents.append(self.download_client.incomplete_dir)
        return parents

    @cached_property  # noqa: V105
    def age(self) -> int:
        """
        Determine the total time since the item was added.

        :return: The duration in seconds.
        """
        return time.time() - self._fields["addedDate"].value

    @cached_property
    def seconds_since_done(self) -> typing.Optional[int]:
        """
        Determine the number of seconds since the item was completely downloaded.

        Best available estimation of total seeding time.

        :return: The duration in seconds.
        """
        if self._fields["leftUntilDone"].value or self._fields["percentDone"].value < 1:
            logger.warning(
                "Can't determine seconds since done, not complete: %r",
                self,
                extra={
                    "runner": self.download_client.runner,
                    "download_hash": self.hashString,
                },
            )
            return 0
        if (
            not (done_date := self._fields["doneDate"].value)
            and self._fields["addedDate"].value
        ):
            # I've seen cases where almost half of torrents that I confirmed were
            # complete and seeding have no `doneDate`. Maybe this happens when adding a
            # torrent when the local data is already complete, AKA adding a seed?
            # Regardless of why it happens, it happens so often it's too noisy to log
            # even at the `DEBUG` level:
            logger.warning(
                "Missing done date for seconds since done, using added date: %r",
                self,
                extra={
                    "runner": self.download_client.runner,
                    "download_hash": self.hashString,
                },
            )
            done_date = self._fields["addedDate"].value
        if done_date and done_date > 0:
            return time.time() - done_date

        logger.warning(
            "Missing done date for seconds since done: %r",
            self,
            extra={
                "runner": self.download_client.runner,
                "download_hash": self.hashString,
            },
        )
        return None

    @cached_property
    def seconds_downloading(self) -> int:
        """
        Determine the number of seconds spent downloading the item.

        Best available estimation of total downloading duration.

        :return: The duration in seconds.
        """
        done_date = self._fields["doneDate"].value
        if done_date == self._fields["addedDate"].value:
            logger.warning(
                "Done date is the same as added date: %r",
                self,
                extra={
                    "runner": self.download_client.runner,
                    "download_hash": self.hashString,
                },
            )
        elif done_date < self._fields["addedDate"].value:
            logger.warning(
                "Done date is before added date: %r",
                self,
                extra={
                    "runner": self.download_client.runner,
                    "download_hash": self.hashString,
                },
            )
        if not done_date:
            done_date = time.time()
            if done_date == self._fields["addedDate"].value:
                logger.warning(  # pragma: no cover
                    "Added date is now: %r",
                    self,
                    extra={
                        "runner": self.download_client.runner,
                        "download_hash": self.hashString,
                    },
                )
            elif done_date < self._fields["addedDate"].value:
                logger.warning(
                    "Added date is in the future: %r",
                    self,
                    extra={
                        "runner": self.download_client.runner,
                        "download_hash": self.hashString,
                    },
                )
        return done_date - self._fields["addedDate"].value

    @cached_property
    def rate_total(self) -> typing.Optional[float]:
        """
        Determine the total download rate across the whole download time.

        :return: The rate in bytes per second or Bps.
        """
        if (seconds_downloading := self.seconds_downloading) <= 0:
            return None
        return (
            self._fields["sizeWhenDone"].value - self._fields["leftUntilDone"].value
        ) / seconds_downloading

    @cached_property
    def disk_usage(self) -> int:
        """
        Calculate the real storage usage of all files.

        Considering hard links and sparse files.

        :return: The size in bytes or B.
        """
        return sum(
            item_file.disk_usage for item_file in self.files if item_file.path.exists()
        )

    @cached_property
    def log_path(self) -> pathlib.Path:
        """
        Assemble the path for the log file dedicated to this individual download item.

        :return: The log file path object.
        """
        return pathlib.Path(self.download_dir, f"{self.hashString}-prunerr.log")

    @cached_property
    def release(
        self,
    ) -> typing.Optional["prunerr.servarr.release.PrunerrServarrRelease"]:
        """
        Lookup the Servarr release corresponding to this download item if any.

        :return: The Servarr release.
        """
        servarr_download_client = self.download_client.servarrs.get(self.download_dir)
        if servarr_download_client is not None:
            return servarr_download_client.RELEASE_FACTORY(
                servarr_download_client,
                self,
            )
        return None  # pragma: no cover

    def match_indexer_urls(self) -> typing.Optional[str]:
        """
        Return the indexer name if the download item matches a configured tracker URL.

        :return: The first indexer name from the Prunerr configuration that matched if
            any.
        """
        for (
            possible_name,
            possible_hostnames,
        ) in self.download_client.operations.config.get(
            "hostnames",
            {},
        ).items():
            for tracker in self.trackers:
                for action in ("announce", "scrape"):
                    tracker_url = urllib.parse.urlsplit(tracker[action])
                    for indexer_hostname in possible_hostnames:
                        if tracker_url.hostname == indexer_hostname:
                            return possible_name
        return None

    def review(self, operations_type: str = "reviews", **context) -> list:
        """
        Apply review operations to this download item.

        :param operations_type: The key in the Prunerr configuration containing the
            operations.
        :param context: The names and values available when rendering templates.
        :return: Mappings describing the actions taken if any.
        """
        _, sort_key = self.download_client.operations.exec_indexer_operations(
            self,
            operations_type=operations_type,
            **context,
        )
        reviews_indxers = self.download_client.operations.config.get("reviews", [])
        indexer_config = reviews_indxers[sort_key[0]]
        operation_configs = indexer_config.get("operations", [])

        results = []
        for operation_config, sort_value in zip(operation_configs, sort_key[1:]):
            if sort_value:
                # Sort value didn't match review operation requirements
                continue

            if operation_config.get("remove", False):
                result = {"remove": True}
                logger.info(
                    "Removing download item per %r review: %r",
                    operation_config["type"],
                    self,
                )
                if self.release is not None and self.release.queue is not None:
                    delete_params = {}
                    if operation_config.get("blacklist", False):
                        delete_params["blacklist"] = "true"
                        result["blacklist"] = True
                    self.release.servarr_download_client.delete(
                        self.release,
                        **delete_params,
                    )
                else:
                    logger.warning(
                        "Download item not in any Servarr queue: %r",
                        self,
                        extra={
                            "runner": self.download_client.runner,
                            "download_hash": self.hashString,
                        },
                    )
                self.download_client.delete_files(self)
                results.append(result)
                # Avoid race conditions, perform no further operations on removed items
                break

            if "change" in operation_config:  # pylint: disable=magic-value-comparison
                logger.info(
                    "Changing download item per %r review for %r: %s",
                    operation_config["type"],
                    self,
                    json.dumps(operation_config["change"]),
                )
                self.download_client.client.change_torrent(
                    [self.hashString],
                    **operation_config["change"],
                )
                results.append(operation_config["change"])
                self.update()

        return results

    def find_location(self, item_root_paths: list) -> pathlib.Path:
        """
        Find the most downloaded data path for this download item and set location.

        The current implementation guesses the most downloaded path by sorting the
        possible matches by size, largest first, and then modification date, most recent
        first, and selects the first of those sorted paths. Anything more accurate
        requires CPU intensive, time consuming verification.

        :param item_root_paths: Filesystem paths of existing download item data.
        :return: The best data path if the location was changed.
        """
        if self.FIELD_DOWNLOAD_DIR not in self._fields:  # pragma: no cover
            logger.debug(
                "Missing download dir field, updating: %r",
                self,
            )
            self.update()

        def key(item_root_path: pathlib.Path) -> tuple:
            """
            Determine the size and modification date of this items data in the path.

            :param item_root_path: A filesystem path of existing download item data.
            :return: The values on which to sort this sequence item.
            """
            du_process = subprocess.run(  # nosec, pragmatic choice for performance
                ["du", "-s", str(item_root_path)],
                capture_output=True,
                check=True,
            )
            return (
                int(du_process.stdout.strip().split()[0]),
                item_root_path.stat().st_mtime,
            )

        item_root_path = sorted(item_root_paths, reverse=True, key=key)[0]

        if self.download_dir != item_root_path.parent:
            logger.info(
                "Changing download item location for %r: %s",
                self,
                item_root_path.parent,
            )
            self.locate_data(item_root_path.parent)
            # Avoid another RPC request, update the field value using the internals:
            self._fields[self.FIELD_DOWNLOAD_DIR] = transmission_rpc.lib_types.Field(
                str(item_root_path.parent),
                False,
            )
            del self.download_dir
            return item_root_path.parent

        logger.debug(
            "Download item location already best for %r: %s",
            self,
            item_root_path.parent,
        )
        return None

    def link_imported_files(
        self,
        item_root_paths: list,
        imported_root: pathlib.Path,
        imported_relatives: dict,
        need_verify: bool = False,
    ):
        """
        Hard link imported files back into download items.

        :param item_root_paths: Filesystem paths of existing download item data.
        :param imported_root: The path to the series/movie directory containing the
            relative imported file paths.
        :param imported_relatives: Map the relative paths of imported files to the
            corresponding paths within the download item.
        :param need_verify: Optionally pass in whether the caller already knows this
            item needs to be verified after linking.
        :return: The download item file paths of any imported files that were linked
            into the download item.
        :rtype: Iterator[]
        """
        # Change the download item data path if a better one is found.  Collect
        # additional possible data paths from the import history records:
        if not (item_root_paths := list(item_root_paths)):
            logger.debug(
                "No existing download item location found for: %r",
                self,
            )
        elif self.find_location(item_root_paths):
            need_verify = True

        # Hard link imported files into the download item's location:
        file_relatives = set(item_file.relative for item_file in self.files)
        for imported_relative, dropped_data in imported_relatives.items():
            if dropped_data["droppedRel"] not in file_relatives:  # pragma: no cover
                logger.error(
                    "Dropped path doesn't match download item file: %s",
                    dropped_data["droppedRel"],
                )
                continue
            if self.FIELD_DOWNLOAD_DIR not in self._fields:  # pragma: no cover
                logger.debug(
                    "Missing download dir field, updating: %r",
                    self,
                )
                self.update()
            download_file_path = self.download_dir / dropped_data["droppedRel"]
            if maybe_link_file(download_file_path, imported_root / imported_relative):
                need_verify = True
                yield str(download_file_path)

        if need_verify:
            # Deselect for download any remaining incomplete files:
            self.clear()
            self.deselect_unimported_files()

            logger.info(
                "Verifying and resuming download item: %r",
                self,
            )
            self.download_client.client.verify_torrent(
                self.hashString,
            )
            self.start()

    def deselect_unimported_files(self) -> list:
        """
        For any unimported and incomplete files, deselect them for download.

        :return: Map file indexes to ``prunerr.downloaditem.PrunerrDownloadItemFile()``
            instances for any files that were deselected.
        """
        deselected_files = [
            download_file_idx
            for download_file_idx, download_file in enumerate(self.files)
            if (
                not download_file.path.exists()
                or (
                    download_file.stat.st_nlink <= 1
                    and download_file.completed < download_file.size
                )
            )
        ]
        if deselected_files:
            logger.info(
                "Deselecting un-imported, incomplete download files for %r: %r",
                self,
                deselected_files,
            )
            self.download_client.client.change_torrent(
                [self.hashString],
                files_unwanted=deselected_files,
            )
        return deselected_files

    def re_add(self) -> "PrunerrDownloadItem":
        """
        Remove and re-add this download item with the same item files location.

        :return: The new item that results from re-adding this item.
        """
        logger.info(
            "Re-adding download item to client: %r",
            self,
        )
        with open(self.torrentFile, mode="r+b") as torrent_opened:
            self.download_client.client.remove_torrent(ids=[self.hashString])
            re_added = type(self)(
                self.download_client,
                self.download_client.client,
                self.download_client.client.add_torrent(
                    torrent=torrent_opened,
                    # These are the only fields from the `add_torrent()` call signature
                    # in the docs I could see corresponding fields for in the
                    # representation of a torrent.
                    bandwidthPriority=self.bandwidthPriority,
                    download_dir=str(self.download_dir),
                    peer_limit=self.peer_limit,
                ),
            )
        self.download_client.items.append(re_added)
        # Some fields seem not to be populated in the object returned from
        # `client.add_torrent()`:
        re_added.update()
        return re_added

    def re_add_check(self, seeding_dir: pathlib.Path) -> bool:
        """
        Decide and log whether to re-add this download item.

        :param seeding_dir: Download items whose download directory is a descendant of
            this directory should be re-added.
        :return: True if this item should be added, False otherwise.
        """
        if self.status == self.STATUS_CHECKING:  # pragma: no cover
            logger.debug(
                "Not re-adding download item being verified: %r",
                self,
            )
            return False
        if seeding_dir not in self.path.parents:  # pragma: no cover
            logger.debug(
                "Not re-adding download item not in the seeding directory: %r",
                self,
            )
            return False
        if self.progress:  # pragma: no cover
            logger.debug(
                "Not re-adding download item with download progress: %r",
                self,
            )
            return False
        return True


class PrunerrDownloadItemFile(utils.PrunerrComponent):
    """
    Combine Prunerr's download item file access and the RPC client library's.
    """

    def __init__(self, download_item, rpc_file):
        """
        Capture a reference to the RPC client library item file.
        """
        self.download_item = download_item
        self.rpc_file = rpc_file

    def __getattr__(self, name):
        """
        Make `stat()` properties available as attributes.
        """
        try:
            return getattr(self.rpc_file, name)
        except AttributeError:  # pragma: no cover
            return getattr(self.stat, name)

    @property
    def details(self) -> dict:
        """
        Assemble all available useful information.

        :return: Map descriptive names to useful values.
        """
        details = self.rpc_file._asdict()
        details["disk_usage"] = self.disk_usage
        details["imported"] = self.is_imported
        return details

    @cached_property
    def relative(self) -> pathlib.Path:
        """
        Assemble the path for this item file relative to the item root.

        :return: The assembled path.
        """
        return pathlib.Path(self.rpc_file.name)

    @cached_property
    def path(self) -> pathlib.Path:
        """
        Determine this file's path, in the ``download-dir`` or ``incomplete-dir``.

        :return: The path found for this file.
        """
        path = self.download_item.parents[0] / self.relative
        if path.exists():
            return path
        for parent in self.download_item.parents[1:]:
            other_path = parent / self.relative
            if other_path.exists():
                return other_path
        return path

    @cached_property
    def stat(self) -> os.stat_result:
        """
        Lookup item file `stat` metadata only as needed and only once.

        :return: The file's metadata.
        """
        return self.path.stat()

    @cached_property
    def disk_usage(self) -> int:
        """
        Calculate the real storage usage of this file.

        Considering hard links and sparse files.

        :return: The size in bytes or B.
        """
        return (
            (self.stat.st_blocks * 512)
            if (self.path.exists() and self.stat.st_nlink == 1)
            else 0
        )

    @cached_property
    def is_imported(self) -> bool:
        """
        Has this file been imported into the library by hard linking it elsewhere.

        :return: Whether this file has more than one hard link.
        """
        return self.path.exists() and self.stat.st_nlink > 1


def maybe_link_file(source: pathlib.Path, target: pathlib.Path) -> bool:
    """
    Link the source file to the target path if not already linked to it.

    :param source: The path of the file to hard link.
    :param target: The path to hard link the file to.
    :return: ``True`` if the source was hard linked.
    """
    try:
        source.parent.mkdir(parents=True, exist_ok=True)
    except OSError:  # pragma: no cover
        logger.exception(
            "Error creating download item directory: %s",
            source.parent,
        )
        return False
    if source.parent.stat().st_dev != target.parent.stat().st_dev:  # pragma: no cover
        logger.exception(
            "Download item on different filesystem: %r -> %r",
            str(source),
            str(target),
        )
        return False
    if source.exists():
        if source.samefile(target):
            logger.debug(
                "Already hard linked to file: %r -> %r",
                str(source),
                str(target),
            )
            return False
        logger.info(
            "Deleting existing file: %s",
            source,
        )
        source.unlink()
    logger.info(
        "Hard linking file: %r -> %r",
        str(source),
        str(target),
    )
    source.hardlink_to(target)
    return True
