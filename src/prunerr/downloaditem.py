# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Prunerr interaction with download clients.
"""

import os
import typing
import time
import urllib.parse
import logging

import transmission_rpc

from . import utils
from .utils import pathlib
from .utils import cached_property
from . import operations

if typing.TYPE_CHECKING:  # pragma: no cover
    import prunerr.servarr.release

logger = logging.getLogger(__name__)


class PrunerrDownloadItem(
    utils.PrunerrOperationsItem,
    transmission_rpc.Torrent,
):  # pylint: disable=too-many-public-methods
    """
    Enrich download item data from the download client API.
    """

    FIELD_HASH = "hashString"
    FIELD_TRACKERS = "trackers"
    FIELD_DOWNLOAD_DIR = "downloadDir"
    STATUS_DOWNLOADING = "downloading"
    STATUS_SEEDING = "seeding"
    STATUS_SEEDING_INT = 6
    STATUS_CHECKING = "checking"

    def __init__(self, download_client, torrent):
        """
        Reconstitute the native Python representation.
        """
        self.download_client = download_client
        super(utils.PrunerrComponent, self).__init__(fields=torrent.fields)
        self.update(torrent)

    @property
    def details(self) -> dict:
        """
        Assemble all available useful information.

        :return: Map descriptive names to useful values.
        """
        details: dict = {}
        if (name := self.name) is not None:
            details["name"] = name
        elif self.FIELD_HASH in self.fields:  # pragma: no cover
            details["hash"] = self.fields[self.FIELD_HASH].value
        else:  # pragma: no cover
            details["id"] = self.fields["id"]
        if self.FIELD_TRACKERS in self.fields:  # pragma: no cover
            details["indexer"] = self.indexer_config.get("name")
        details["disk_usage"] = utils.format_size(self.disk_usage)
        details["imported"] = f"{round(self.imported_portion * 100)}%"
        return details

    def update(self, torrent: typing.Optional[transmission_rpc.Torrent] = None):
        """
        Update cached values when this download item is updated.

        :param torrent: The underlying torrent object from ``transmission_rpc``.
        """
        if torrent is None:
            torrent = self.download_client.client.get_torrent(
                self.fields["hashString"],
            )
            super(utils.PrunerrComponent, self).__init__(fields=torrent.fields)

        self.files = []
        self.files_by_relative = {}
        for rpc_file in super().get_files():
            item_file = PrunerrDownloadItemFile(self, rpc_file)
            self.files.append(item_file)
            self.files_by_relative[item_file.relative] = item_file

        super().update()

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
                logger.warning(
                    "Files in %r have multiple roots, using: %s",
                    self.name,
                    file_roots[0],
                    extra={
                        "runner": self.download_client.runner,
                        "download_hash": self.hash_string,
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
        return time.time() - self.fields["addedDate"]

    @cached_property
    def seconds_since_done(self) -> typing.Optional[int]:
        """
        Determine the number of seconds since the item was completely downloaded.

        Best available estimation of total seeding time.

        :return: The duration in seconds.
        """
        if self.fields["leftUntilDone"] or self.fields["percentDone"] < 1:
            logger.warning(
                "Can't determine seconds since done, not complete: %r",
                self,
                extra={
                    "runner": self.download_client.runner,
                    "download_hash": self.hash_string,
                },
            )
            return 0
        if not (done_date := self.fields["doneDate"]) and self.fields["addedDate"]:
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
                    "download_hash": self.hash_string,
                },
            )
            done_date = self.fields["addedDate"]
        if done_date and done_date > 0:
            return time.time() - done_date

        logger.warning(
            "Missing done date for seconds since done: %r",
            self,
            extra={
                "runner": self.download_client.runner,
                "download_hash": self.hash_string,
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
        done_date = self.fields["doneDate"]
        if done_date == self.fields["addedDate"]:
            logger.warning(
                "Done date is the same as added date: %r",
                self,
                extra={
                    "runner": self.download_client.runner,
                    "download_hash": self.hash_string,
                },
            )
        elif done_date < self.fields["addedDate"]:
            logger.warning(
                "Done date is before added date: %r",
                self,
                extra={
                    "runner": self.download_client.runner,
                    "download_hash": self.hash_string,
                },
            )
        if not done_date:
            done_date = time.time()
            if done_date == self.fields["addedDate"]:
                logger.warning(  # pragma: no cover
                    "Added date is now: %r",
                    self,
                    extra={
                        "runner": self.download_client.runner,
                        "download_hash": self.hash_string,
                    },
                )
            elif done_date < self.fields["addedDate"]:
                logger.warning(
                    "Added date is in the future: %r",
                    self,
                    extra={
                        "runner": self.download_client.runner,
                        "download_hash": self.hash_string,
                    },
                )
        return done_date - self.fields["addedDate"]

    @cached_property
    def rate_total(self) -> typing.Optional[float]:
        """
        Determine the total download rate across the whole download time.

        :return: The rate in bytes per second or Bps.
        """
        if (seconds_downloading := self.seconds_downloading) <= 0:
            return None
        return (self.size_selected - self.fields["leftUntilDone"]) / seconds_downloading

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
    def size_selected(self) -> float:
        """
        Calculate the total size of files that are selected or wanted for download.

        Unfortunately, ``sizeWhenDone`` can't be used because it's the size of the files
        that were selected when this item first finished downloading. So if files were
        de-selected later, then ``sizeWhenDone`` is larger than the total size of
        selected files.

        :return: The total size in bytes or B.
        """
        return sum(item_file.size for item_file in self.files if item_file.selected)

    @cached_property
    def size_imported(self) -> float:
        """
        Calculate the total size of selected files that are hard lined elsewhere.

        :return: The total size in bytes or B.
        """
        return sum(
            item_file.size
            for item_file in self.files
            if item_file.selected and item_file.is_imported
        )

    @cached_property
    def imported_portion(self) -> float:
        """
        Calculate the portion of this item's size that is currently imported.

        :return: The size in bytes or B.
        """
        return self.size_imported / self.size_selected if self.size_selected else 0.0

    @cached_property
    def log_path(self) -> pathlib.Path:
        """
        Assemble the path for the log file dedicated to this individual download item.

        :return: The log file path object.
        """
        return pathlib.Path(self.download_dir, f"{self.hash_string}-prunerr.log")

    @cached_property
    def release(
        self,
    ) -> typing.Optional["prunerr.servarr.release.PrunerrServarrRelease"]:
        """
        Lookup the Servarr release corresponding to this download item if any.

        :return: The Servarr release.
        """
        for servarr_download_client in self.download_client.servarrs.values():
            if servarr_download_client.is_release(self):
                return servarr_download_client.RELEASE_FACTORY(
                    servarr_download_client,
                    self,
                )
        return None  # pragma: no cover

    @cached_property
    def indexer_config(self) -> dict:
        """
        Return the indexer name if the download item matches a configured tracker URL.

        :return: The first indexer name from the Prunerr configuration that matched if
            any.
        """
        for tracker in self.trackers:
            for action in ("announce", "scrape"):
                tracker_url = urllib.parse.urlsplit(getattr(tracker, action))
                for indexer_config in self.download_client.runner.config[
                    "indexers"
                ].values():
                    for indexer_hostname in indexer_config["hostnames"]:
                        if tracker_url.hostname == indexer_hostname:
                            return indexer_config["config"]
        return {}

    # Methods involved in life-cycle stage operations:

    def apply_remove(  # noqa: V105
        self,
        operation: operations.PrunerrOperation,
        **context,  # pylint: disable=unused-argument
    ) -> str:
        """
        Remove this download item according to the operation configuration.

        :param operation: The operation configuration from the configuration file YAML.
        :param context: Additional names and values available in templates.
        :return: The filesystem path of the removed download item.
        """
        logger.info(
            "Removing download item per %r operation: %r",
            operation.config["name"],
            self,
        )
        self.download_client.delete_files(self)
        operation.stage.items.remove(self)
        return str(self.path)

    def apply_change(  # noqa: V105
        self,
        operation: operations.PrunerrOperation,
        **context,  # pylint: disable=unused-argument
    ) -> dict:
        """
        Change this download item's fields according to the operation configuration.

        :param operation: The operation configuration from the configuration file YAML.
        :param context: Additional names and values available in templates.
        :return: ``True`` since the changes are always applied.
        """
        logger.info(
            "Changing download item per %r operation for %r: %s",
            operation.config["name"],
            self,
            repr(operation.config[operations.ACTION_CHANGE]),
        )
        self.download_client.client.change_torrent(
            [self.hash_string],
            **operation.config[operations.ACTION_CHANGE],
        )
        self.update()
        return operation.config[operations.ACTION_CHANGE]

    def apply_move(  # noqa: V105
        self,
        operation: operations.PrunerrOperation,
        move_timeout: int = 5 * 60,
        **context,
    ) -> typing.Optional[str]:
        """
        Move this download item according to the operation configuration.

        :param operation: The operation configuration from the configuration file YAML.
        :param context: Additional names and values available in templates.
        :param move_timeout: How long to wait for the release to be moved in the
            download client before continuing.
        :return: The download items new ``downloadDir``.
        :raises DownloadClientTimeout: Moving the download item took too long.
        """
        new_download_dir = operation.config[operations.ACTION_MOVE].render(
            item=self,
            **context,
        )
        if new_download_dir == self.download_dir:
            logger.debug(
                "Download item already moved: %r -> %r",
                self,
                str(new_download_dir),
            )
            return None

        logger.info(
            "Moving download item %r: %r -> %r",
            self,
            str(self.download_dir),
            str(new_download_dir),
        )
        self.download_client.client.move_torrent_data(
            ids=[self.hash_string],
            location=new_download_dir,
        )
        old_path = self.path
        old_log_path = self.log_path
        # Update the download item's dir for subsequent operations, done manually to
        # minimize requests.
        self.fields[self.FIELD_DOWNLOAD_DIR] = new_download_dir
        self.clear()
        # Move any log files along with the item:
        if old_log_path.exists():
            old_log_path.rename(self.log_path)
        # Wait for a timeout for items to finish moving before proceeding.
        start = time.time()
        while old_path.exists():  # pylint: disable=while-used
            if time.time() - start > move_timeout:
                raise self.download_client.TIMEOUT_EXCEPTION(
                    f"Timed out waiting for {self!r} to finish moving",
                )
            time.sleep(1)
        return str(new_download_dir)

    def apply_verify(  # noqa: V105
        self,
        operation: operations.PrunerrOperation,
        **context,  # pylint: disable=unused-argument
    ) -> dict:
        """
        Verify corrupt data in this download item per the operation configuration.

        :param operation: The operation configuration from the configuration file YAML.
        :param context: Additional names and values available in templates.
        :return: ``True`` since verification is always started.
        """
        logger.info(
            "Verifying corrupt download item: %r",
            self,
        )
        self.download_client.client.verify_torrent([self.hash_string])
        return operation.config[operations.ACTION_VERIFY]

    def apply_log(  # noqa: V105
        self,
        operation: operations.PrunerrOperation,
        **context,
    ) -> dict:
        """
        Log a message from a template per the operation configuration.

        Usually, this is used to send a notification when `ntfy` is configured.

        :param operation: The operation configuration from the configuration file YAML.
        :param context: Additional names and values available in templates.
        :return: A mapping describing the messages logged.
        """
        context["item"] = self
        log_result = {
            "level": logging._nameToLevel[  # pylint: disable=protected-access
                operation.config.get("level", "ERROR")
            ],
            "msg": operation.config[operations.ACTION_LOG].render(**context),
        }
        logger.log(
            log_result["level"],
            log_result["msg"],
            (
                operation.config[operations.ACTION_ARG].render(**context)
                if operations.ACTION_ARG in operation.config
                else context
            ),
        )
        return log_result

    def apply_un_import(  # noqa: V105
        self,
        operation: operations.PrunerrOperation,
        **context,  # pylint: disable=unused-argument
    ) -> typing.Optional[list]:
        """
        Remove and hard links to this release's files in its Servarr library.

        :param operation: The operation configuration from the configuration file YAML.
        :param context: Additional names and values available in templates.
        :return: The paths of any imported files that were un-linked.
        """
        if self.release is not None and not self.release.queue:
            return [
                str(un_imported_item["file"]["path"])
                for un_imported_item in self.release.un_import().values()
            ]
        logger.debug(  # pragma: no cover
            "Cannot un-import, not an imported Servarr release: %r",
            self,
        )
        return None  # pragma: no cover

    def apply_de_queue(  # noqa: V105
        self,
        operation: operations.PrunerrOperation,
        **context,  # pylint: disable=unused-argument
    ) -> typing.Optional[int]:
        """
        Remove this release from the Servarr queue per the operation configuration.

        Only applies this action if the download item is a Servarr release and is in its
        Servarr queue.

        :param operation: The operation configuration from the configuration file YAML.
        :param context: Additional names and values available in templates.
        :return: The DB ID for the episode/movie removed from the queue.
        """
        if (
            self.release is not None
            and self.download_dir == self.release.servarr_download_client.download_dir
            and self.release.queue
        ):
            servarr = self.release.servarr_download_client.servarr
            type_map = servarr.type_map
            return self.release.de_queue(
                **operation.config[operations.ACTION_DE_QUEUE]
            )[f"{type_map['item_type']}Id"]
        logger.debug("Not in the Servarr queue: %r", self)
        return None

    def apply_fail(  # noqa: V105
        self,
        operation: operations.PrunerrOperation,
        **context,  # pylint: disable=unused-argument
    ) -> typing.Optional[int]:
        """
        Mark this release's Servarr `grabbed` history record as failed, start a search.

        Only applies this action if the download item is a Servarr release and is not in
        its Servarr queue.

        :param operation: The operation configuration from the configuration file YAML.
        :param context: Additional names and values available in templates.
        :return:
            The DB ID for the episode/movie whose ``grabbed`` record was marked as
            failed.
        """
        if self.release is not None and self.release.grabbed is not None:
            return self.release.fail()["sourceTitle"]
        logger.debug("Not grabbed by Servarr: %r", self)  # pragma: no cover
        return None  # pragma: no cover

    # Other methods:

    def re_add(self) -> "PrunerrDownloadItem":
        """
        Remove and re-add this download item with the same item files location.

        :return: The new item that results from re-adding this item.
        """
        logger.info(
            "Re-adding download item to client: %r",
            self,
        )
        with open(self.torrent_file, mode="r+b") as torrent_opened:
            self.download_client.client.remove_torrent(ids=[self.hash_string])
            re_added = type(self)(
                self.download_client,
                self.download_client.client.add_torrent(
                    torrent=torrent_opened,
                    # These are the only fields from the `add_torrent()` call signature
                    # in the docs I could see corresponding fields for in the
                    # representation of a torrent.
                    bandwidthPriority=self.bandwidth_priority,
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
        details = {
            "path": self.rpc_file.name,
            "disk_usage": utils.format_size(self.disk_usage),
            "imported": self.is_imported,
        }
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

    @cached_property
    def is_servarr_extra(self) -> bool:
        """
        Is this an extra file that Servarr imports.

        :return: Whether this file is a Servarr extra import.
        """
        if self.download_item.release is not None:
            servarr = self.download_item.release.servarr_download_client.servarr
            return self.relative.suffix in servarr.extra_file_suffixes
        return False  # pragma: no cover

    @cached_property
    def queued_upgrades(self) -> dict:
        """
        Map the queued releases that will upgrade this file when imported.

        Only available for download items in the ``upgraded`` stage.

        :return: Map queued release download item hash IDs to the queued release item
            files that will upgrade this file.
        :raises NotImplementedError: There's a problem with the conditions that prevents
            identifying queued upgrades.
        """
        raise NotImplementedError(  # pragma: no cover
            "Cannot identify queued upgrades outside the ``upgraded`` stage"
            f": {self!r}",
        )
