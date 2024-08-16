# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

# pylint: disable=missing-any-param-doc,missing-param-doc,missing-return-doc
# pylint: disable=missing-return-type-doc,missing-type-doc

"""
Prunerr interaction with download clients.
"""

import os
import time
import urllib.parse
import json
import subprocess  # nosec, pragmatic choice for performance
import logging

import transmission_rpc

from .utils import pathlib
from .utils import cached_property

logger = logging.getLogger(__name__)


def parallel_to(base_path, parallel_path, root_basename):
    """
    Return a path with a parallel relative root to the given full path.
    """
    base_path = pathlib.Path(base_path)
    common_path = pathlib.Path(os.path.commonpath((base_path.parent, parallel_path)))
    return (
        common_path
        / root_basename
        / pathlib.Path(parallel_path).relative_to(
            list(parallel_path.parents)[-(len(base_path.parts))],
        )
    )


class PrunerrDownloadItem(transmission_rpc.Torrent):
    """
    Enrich download item data from the download client API.
    """

    DOWNLOAD_DIR_FIELD = "downloadDir"

    def __init__(self, download_client, client, torrent):
        """
        Reconstitute the native Python representation.
        """
        self.download_client = download_client
        super().__init__(
            client,
            {field_name: field.value for field_name, field in torrent._fields.items()},
        )

    def update(self, timeout=None):
        """
        Update cached values when this download item is updated.
        """
        super().update(timeout=timeout)
        vars(self).pop("path", None)

    @cached_property
    def root_name(self):
        """
        Return the name of the first path element for all items in the download item.

        Needed because it's not always the same as the item's name.  If the download
        item has multiple files, assumes that all files are under the same top-level
        directory.
        """
        file_roots = list(
            {item_file.relative.parts[0]: None for item_file in self.files}
        )
        if file_roots:
            if len(set(file_roots)) > 1:
                logger.error(
                    "Files in %r have multiple roots, using: %s",
                    self,
                    file_roots[0],
                    extra={"runner": self.download_client.runner},
                )
            return file_roots[0]
        return self.name

    @cached_property
    def path(self):
        """
        Return the root path for all files in the download item.

        Needed because it's not always the same as the item's download directory plus
        the item's name.
        """
        return (pathlib.Path(self.download_dir) / self.root_name).resolve()

    @cached_property
    def files_parent(self):
        """
        Determine the path in which the download item's files are currently stored.

        This may be the `incomplete_dir` while the item is downloading.
        """
        files_parent = pathlib.Path(self.download_dir) / self.root_name
        if (
            self.download_client.client.session.incomplete_dir_enabled
            and not files_parent.exists()
        ):
            files_parent = (
                pathlib.Path(self.download_client.client.session.incomplete_dir)
                / files_parent.name
            )
        return files_parent.resolve()

    @cached_property  # noqa: V105
    def age(self):
        """
        Determine the total time since the item was added.
        """
        return time.time() - self._fields["addedDate"].value

    @cached_property
    def seconds_since_done(self):
        """
        Determine the number of seconds since the item was completely downloaded.

        Best available estimation of total seeding time.
        """
        if self._fields["leftUntilDone"].value or self._fields["percentDone"].value < 1:
            logger.warning(
                "Can't determine seconds since done, not complete: %r",
                self,
            )
            return None
        if not (done_date := self._fields["doneDate"].value):
            if self._fields["startDate"].value:
                logger.warning(
                    "Missing done date for seconds since done, using start date: %r",
                    self,
                )
                done_date = self._fields["startDate"].value
            elif self._fields["addedDate"].value:
                logger.warning(
                    "Missing done date for seconds since done, using added date: %r",
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

    @cached_property
    def seconds_downloading(self):
        """
        Determine the number of seconds spent downloading the item.

        Best available estimation of total downloading duration.
        """
        done_date = self._fields["doneDate"].value
        if done_date == self._fields["addedDate"].value:
            logger.warning(
                "Done date is the same as added date: %r",
                self,
                extra={"runner": self.download_client.runner},
            )
        elif done_date < self._fields["addedDate"].value:
            logger.warning(
                "Done date is before added date: %r",
                self,
                extra={"runner": self.download_client.runner},
            )
        if not done_date:
            done_date = time.time()
            if done_date == self._fields["addedDate"].value:
                logger.warning(  # pragma: no cover
                    "Added date is now: %r",
                    self,
                    extra={"runner": self.download_client.runner},
                )
            elif done_date < self._fields["addedDate"].value:
                logger.warning(
                    "Added date is in the future: %r",
                    self,
                    extra={"runner": self.download_client.runner},
                )
        return done_date - self._fields["addedDate"].value

    @cached_property
    def rate_total(self):
        """
        Determine the total download rate across the whole download time.
        """
        if (seconds_downloading := self.seconds_downloading) <= 0:
            return None
        return (
            self._fields["sizeWhenDone"].value - self._fields["leftUntilDone"].value
        ) / seconds_downloading

    @cached_property
    def files(self):  # pylint: disable=invalid-overridden-method,useless-suppression
        """
        Iterate over all download item file paths that exist.
        """
        return [PrunerrDownloadItemFile(self, rpc_file) for rpc_file in super().files()]

    def match_indexer_urls(self):
        """
        Return the indexer name if the download item matches a configured tracker URL.
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

    def review(self, servarr_queue):
        """
        Apply review operations to this download item.
        """
        _, sort_key = self.download_client.operations.exec_indexer_operations(
            self,
            operations_type="reviews",
        )
        reviews_indxers = self.download_client.operations.config.get("reviews", [])
        indexer_config = reviews_indxers[sort_key[0]]
        operation_configs = indexer_config.get("operations", [])

        download_id = self.hashString.upper()
        queue_record = servarr_queue.get(download_id, {})
        queue_id = queue_record.get("id")

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
                if not queue_record:
                    logger.warning(
                        "Download item not in any Servarr queue: %r",
                        self,
                        extra={"runner": self.download_client.runner},
                    )
                else:
                    delete_params = {}
                    if operation_config.get("blacklist", False):
                        delete_params["blacklist"] = "true"
                        result["blacklist"] = True
                    queue_record["servarr"].client.delete(
                        f"queue/{queue_id}",
                        **delete_params,
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

    def find_location(self, data_paths):
        """
        Find the most downloaded data path for this download item and set location.

        The current implementation guesses the most downloaded path by sorting the
        possible matches by size, largest first, and then modification date, most recent
        first, and selects the first of those sorted paths. Anything more accurate
        requires CPU intensive, time consuming verification.

        :param data_paths: Paths to directories whose direct or immediate children are
            checked for existing download item data.
        :return: A ``pathlib.Path()`` object to the best data path if the location was
            changed.
        """

        def key(data_path, self=self):
            """
            Determine the size and modification date of this items data in the path.
            """
            item_path = data_path / self.root_name
            du_process = subprocess.run(  # nosec, pragmatic choice for performance
                ["du", "-s", str(item_path)],
                capture_output=True,
                check=True,
            )
            return (
                int(du_process.stdout.strip().split()[0]),
                item_path.stat().st_mtime,
            )

        locations = [
            data_path
            for data_path in data_paths
            if (data_path / self.root_name).exists()
        ]
        if not locations:  # pragma: no cover
            logger.debug(
                "No existing download item location found for: %r",
                self,
            )
            return None
        location = sorted(locations, reverse=True, key=key)[0]
        if self.DOWNLOAD_DIR_FIELD not in self._fields:  # pragma: no cover
            logger.debug(
                "Missing download dir field, updating: %r",
                self,
            )
            self.update()
        if pathlib.Path(self.download_dir) != location:
            logger.info(
                "Changing download item location for %r: %s",
                self,
                location,
            )
            self.locate_data(location)
            # Avoid another RPC request, update the field value using the internals:
            self._fields[self.DOWNLOAD_DIR_FIELD] = transmission_rpc.lib_types.Field(
                str(location),
                False,
            )
            return location

        logger.debug(
            "Download item location already best for %r: %s",
            self,
            location,
        )
        return None

    def link_imported_files(
        self,
        data_paths,
        imported_root,
        imported_relatives,
        need_verify=False,
    ):
        """
        Hard link imported files back into download items.

        :param data_paths: The full list of data paths including those from the Servarr
            download clients.
        :param imported_root: The path to the series/movie directory containing the
            relative imported file paths.
        :param imported_relatives: Map the relative paths of imported files to the
            corresponding paths within the download item.
        :return: The download item file paths of any imported files that were linked
            into the download item.
        :rtype: Iterator[]
        """
        # Change the download item data path if a better one is found.  Collect
        # additional possible data paths from the import history records:
        item_data_paths = dict.fromkeys(data_paths)
        for imported_relative, dropped_data in imported_relatives.items():
            item_data_paths[dropped_data["location"]] = None
        if self.find_location(list(item_data_paths)):
            need_verify = True

        # Hard link imported files into the download item's location:
        for imported_relative, dropped_data in imported_relatives.items():
            if self.DOWNLOAD_DIR_FIELD not in self._fields:  # pragma: no cover
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
            self.deselect_unimported_files()

            logger.info(
                "Verifying and resuming download item: %r",
                self,
            )
            self.download_client.client.verify_torrent(
                self.hashString,
            )
            self.start()

    def deselect_unimported_files(self):
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


class PrunerrDownloadItemFile:
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
        except AttributeError:
            return getattr(self.stat, name)

    @cached_property
    def relative(self):
        """
        Assemble a `pathlib` path for this item file relative to the item root.
        """
        return pathlib.Path(self.rpc_file.name)

    @cached_property
    def path(self):
        """
        Assemble a `pathlib` path for this item file only as needed and only once.
        """
        return self.download_item.path.parent / self.relative

    @cached_property
    def stat(self):
        """
        Lookup item file `stat` metadata only as needed and only once.
        """
        if self.path.exists():
            return self.path.stat()
        return None

    @cached_property  # noqa: V105
    def size_imported(self):
        """
        Return the file's size if the file has more than one hard link.
        """
        if self.stat is not None and self.st_nlink > 1:
            return self.st_size
        return 0


def maybe_link_file(source, target):
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
