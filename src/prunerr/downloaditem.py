"""
Prunerr interaction with download clients.
"""

import os
import time
import urllib.parse
import json
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
        file_roots = [pathlib.Path(item_file.name).parts[0] for item_file in self.files]
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
        done_date = self._fields["doneDate"].value
        if not done_date:
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
        seconds_downloading = self.seconds_downloading
        if seconds_downloading <= 0:
            return None
        return (
            self._fields["sizeWhenDone"].value - self._fields["leftUntilDone"].value
        ) / seconds_downloading

    @cached_property
    def files(self):  # pylint: disable=invalid-overridden-method,useless-suppression
        """
        Iterate over all download item file paths that exist.

        Optionally filter the list by those that are selected in the download client.
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

            if "change" in operation_config:
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
    def path(self):
        """
        Assemble a `pathlib` path for this item file only as needed and only once.
        """
        return self.download_item.path.parent / self.rpc_file.name

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
