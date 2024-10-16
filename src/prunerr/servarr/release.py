# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT


"""
Prunerr interaction with Servarr instances.
"""

import collections
import typing
import logging

from .. import utils
from ..utils import cached_property
from . import rootitem

logger = logging.getLogger(__name__)


class PrunerrServarrRelease(utils.PrunerrComponent):
    """
    A specific Servar instance's individual download item.
    """

    QUEUED_UPGRADES_ATTR = "queued_upgrades"
    UPGRADED_RELEASE_ATTR = "upgraded_release"

    def __init__(self, servarr_download_client, download_item):
        """
        Capture references to the servarr download client and the download item.
        """
        self.servarr_download_client = servarr_download_client
        self.download_item = download_item

    @property
    def details(self) -> dict:
        """
        Assemble all available useful information.

        :return: Map descriptive names to useful values.
        """
        details = {
            "servarr": self.servarr_download_client.servarr.config.get("name"),
            "dowload_client": (
                self.servarr_download_client.download_client.config["name"]
                if hasattr(self.servarr_download_client, "download_client")
                else self.servarr_download_client.config.get("url")
            ),
        }
        details.update(self.download_item.details)
        return details

    def clear(self):
        """
        Reset derived attributes cached in this instance.
        """
        super().clear()
        self.download_item.clear()

    @cached_property
    def queue(self) -> dict:
        """
        Lookup this release's queue records from it's Servarr instance.

        :return: The Servarr API ``queue`` endpoint JSON for this release.
        """
        return self.servarr_download_client.servarr.queue.get(
            self.download_item.hash_string.upper(),
            {},
        )

    @cached_property
    def history(self) -> dict:
        """
        Lookup and collate this download item's Servarr history records.

        :return:
            Map Servarr event types to the Servarr movie/episode DB IDs to the most
            recent Servarr API JSON history record.
        """
        servarr = self.servarr_download_client.servarr
        type_map = servarr.type_map
        history: dict = {}
        for history_record in servarr.get_api_paged_records(
            "history",
            downloadId=self.download_item.hash_string.upper(),
        ):
            if history_record["eventType"] == servarr.EVENT_TYPE_IMPORTED:
                servarr.deserialize_import_record(history_record)
            elif (
                history_record["eventType"] == servarr.EVENT_TYPE_GRABBED
            ):  # pragma: no cover
                servarr.deserialize_grab_record(history_record)
            history.setdefault(history_record["eventType"], {}).setdefault(
                history_record[f"{type_map['item_type']}Id"],
                history_record,
            )
        return history

    @cached_property
    def grabbed(self) -> typing.Optional[dict]:
        """
        Find he most recent grabbed record for this release if any.

        :return: The Servarr API JSON record if found.
        """
        servarr = self.servarr_download_client.servarr
        if grabbed_records := list(
            self.history.get(servarr.EVENT_TYPE_GRABBED, {}).values(),
        ):
            return grabbed_records[0]
        return None  # pragma: no cover

    @cached_property
    def root_item(self) -> rootitem.PrunerrServarrRootItem:
        """
        Lookup the series/movie for this release if any by the most efficient means.

        :return: The Prunerr root item instance.
        :raises ValueError:
          Something in the Servarr data prevents identifying the root item.
        """
        # Start with the queue which is just one request per Servarr instance:
        root_id = self.find_root_id(self.queue)

        # If not in a Servarr queue, try the Servarr history for this specific release,
        # which is one request per release:
        if root_id is None:
            # BBB: Python 3.9 and 3.8 report this as a branch coverage hole:
            for history_records in self.history.values():  # pragma: no cover
                if (root_id := self.find_root_id(history_records)) is not None:
                    break

        if root_id is None:
            raise ValueError(  # pragma: no cover
                f"Cannot determine release's root item: {self!r}",
            )
        return self.servarr_download_client.servarr.get_root_item(root_id)

    def find_root_id(self, record_source: dict) -> typing.Optional[int]:
        """
        Look for the episode/movie DB ID in Servarr queue or history records.

        :param record_source: The Servarr API queue or history record.
        :return: The imported item DB ID if found.
        """
        type_map = self.servarr_download_client.servarr.type_map
        root_id = None
        for record in record_source.values():
            if root_id is None:
                root_id = record[f"{type_map['dir_type']}Id"]
            elif record[f"{type_map['dir_type']}Id"] != root_id:  # pragma: no cover
                logger.warning(
                    "More than one Servarr root item for %r: %r -> %r",
                    self,
                    root_id,
                    record[f"{type_map['dir_type']}Id"],
                )
                break
        return root_id

    @cached_property
    def imported_release_files(self) -> dict:
        """
        Collate the imported release files that this release will upgrade when imported.

        :return:
          Map imported release download item hash IDs to relative item file paths to the
          download item files.
        """
        imported_release_files: dict = {}
        servarr = self.servarr_download_client.servarr
        for imported_item_id, queue_record in self.queue.items():
            # Sonarr seems to include `episodeHasFile` for all records, but the test
            # fixture records do not indicating it may have been added recently. Radarr
            # doesn't have `movieHasFile` at all. So use it if available but if not,
            # assume it says nothing either way:
            if not (
                queue_record.get(
                    f"{servarr.type_map['item_type']}HasFile",
                    True,
                )
            ) or (
                (imported_item := self.root_item.imported_items.get(imported_item_id))
                is None
            ):  # pragma: no cover
                # This episode/movie is not currently imported, there is no release that
                # will be upgraded when this queued release is imported:
                logger.debug(
                    "No imported file %r for queued release %r: %s",
                    imported_item_id,
                    queue_record["title"],
                    queue_record["downloadId"],
                    extra={
                        "runner": self.download_item.download_client.runner,
                        "download_hash": self.download_item.hash_string,
                    },
                )
                continue

            imported_file_stat = imported_item["file"]["path"].stat()
            if not imported_file_stat.st_nlink > 1:  # pragma: no cover
                logger.warning(
                    "Imported file has no hard links: %s",
                    imported_item["id"],
                    extra={
                        "runner": self.download_item.download_client.runner,
                        "download_hash": self.download_item.hash_string,
                    },
                )
                continue

            if not (
                dropped_relative := self.root_item.history.imported_ids.get(
                    imported_item["id"],
                    {},
                ).get("droppedRel")
            ):  # pragma: no cover
                logger.warning(
                    "No dropped path history for imported file: %s",
                    imported_item["id"],
                    extra={
                        "runner": self.download_item.download_client.runner,
                        "download_hash": self.download_item.hash_string,
                    },
                )
                continue

            found_item_file = False
            for servarr_download_client in servarr.download_clients.values():
                client_item_files = (
                    servarr_download_client.download_client.item_files.get(
                        dropped_relative,
                        {},
                    )
                )
                for item_file in client_item_files.values():
                    if item_file.download_item.release and item_file.path.samefile(
                        imported_item["file"]["path"]
                    ):
                        imported_release_files.setdefault(
                            item_file.download_item.hash_string,
                            (item_file.download_item.release, {}),
                        )[1][dropped_relative] = item_file
                        found_item_file = True
                    else:
                        pass  # pragma: no cover
            if not found_item_file:  # pragma: no cover
                logger.warning(
                    "No download item file for imported file: %s",
                    imported_item["id"],
                    extra={
                        "runner": self.download_item.download_client.runner,
                        "download_hash": self.download_item.hash_string,
                    },
                )
                continue

        return imported_release_files

    @cached_property
    def queued_upgrades(self) -> dict:
        """
        Map the queued releases that will upgrade files in this release when imported.

        Only available for download items in the ``upgraded`` stage.

        :return: Map queued release download item hash IDs to the queued releases that
            will upgrade files in this release's download item.
        :raises NotImplementedError: There's a problem with the conditions that prevents
            identifying queued upgrades.
        """
        raise NotImplementedError(  # pragma: no cover
            f"Cannot identify queued upgrades outside the ``upgraded`` stage"
            f": {self!r}",
        )

    @cached_property
    def upgraded_release(self) -> "PrunerrServarrRelease":
        """
        Simulate the state of this release after queued releases upgrade it.

        Only available for download items in the ``upgraded`` stage.

        :return: The Servarr release.
        :raises NotImplementedError: There's a problem with the conditions that prevents
            simulating an upgrade.
        """
        raise NotImplementedError(  # pragma: no cover
            "Cannot simulate upgrade outside the ``upgraded`` life-cycle stage"
            f": {self!r}",
        )

    def filter_upgraded(self) -> collections.abc.Generator:
        """
        Identify the releases this release will upgrade when imported.

        :return: The ``prunerr.downloaditem.PrunerrDownloadItem()`` instances.
        """
        # This is sort of a many-to-many issue. A queued release may upgrade multiple
        # imported releases, such as a season pack queued release upgrading individual
        # episode imported releases. Conversely, a `WEB-DL` season pack imported release
        # may be upgraded by multiple `Bluray` single episode queued releases. So
        # collate the required data for *this* queued release but in such a way that it
        # can be supplemented by other queued releases.

        # First group the imported files that will be upgraded by the currently imported
        # releases they were imported from:
        for imported_release, imported_files in self.imported_release_files.values():

            # Now use the grouped imported files to simulate the state of the imported
            # item after it has been upgraded by importing the queued release and review
            # it:

            # Share one simulated upgraded release for all the queued releases that will
            # upgrade it:
            if imported_release.UPGRADED_RELEASE_ATTR not in vars(  # pragma: no cover
                imported_release
            ):
                imported_release.upgraded_release = type(imported_release)(
                    imported_release.servarr_download_client,
                    type(imported_release.download_item)(
                        imported_release.download_item.download_client,
                        imported_release.download_item,
                    ),
                )
            if self.QUEUED_UPGRADES_ATTR not in vars(  # pragma: no cover
                imported_release
            ):
                imported_release.queued_upgrades = {}
            imported_release.queued_upgrades.setdefault(
                self.download_item.hash_string.upper(),
                self,
            )

            # Map the imported release's files to the queued releases that will upgrade
            # them:
            for dropped_relative, imported_file in imported_files.items():
                if self.QUEUED_UPGRADES_ATTR not in vars(  # pragma: no cover
                    imported_file
                ):
                    imported_file.queued_upgrades = {}
                imported_file.queued_upgrades[
                    self.download_item.hash_string.upper()
                ] = self

                # Decrement the hard link count for all the files of the imported
                # release that will be upgraded by this queued release and replace the
                # cached `imported_file.stat()` results:
                imported_release.upgraded_release.download_item.files_by_relative[
                    dropped_relative
                ].stat = PatchedStatResult(
                    imported_file.stat,
                    st_nlink=imported_file.stat.st_nlink - 1,
                )

            yield imported_release.download_item

    def de_queue(self, **params) -> dict:
        """
        Remove this release from the Servarr queue.

        :param params: The parameters for the Servarr ``queue`` API endpoint.
        :return: The Servarr API JSON for the queue record that was deleted.
        :raises ValueError: Something went wrong sending the API request.
        """
        if not self.queue:
            raise ValueError(f"No queue record for: {self!r}")  # pragma: no cover
        queue_record = list(self.queue.values())[0]
        if (queue_id := queue_record.get("id")) is None:
            raise ValueError(  # pragma: no cover
                f"Queue record missing DB ID: {queue_record!r}",
            )
        self.servarr_download_client.servarr.client.delete(
            f"queue/{queue_id}",
            **params,
        )
        return queue_record

    def fail(self) -> dict:
        """
        Mark this release as failed in Servarr and start a search for a replacement.

        :return:
            The Servarr API JSON for the ``grabbed`` history record that was marked as
            failed.
        :raises ValueError: Something went wrong sending the API request.
        """
        if self.grabbed is None:
            raise ValueError(f"No grab history for: {self!r}")  # pragma: no cover
        self.servarr_download_client.servarr.client.post(
            f"history/failed/{self.grabbed['id']}",
        )
        return self.grabbed

    def un_import(self) -> dict:
        """
        Remove and hard links to this release's files in its Servarr library.

        :return: The Servarr API JSON for the imported items whose files were un-linked.
        :raises ValueError: Something went wrong sending the API request.
        """
        servarr = self.servarr_download_client.servarr

        # Check each file in this release against every imported file to identify the
        # release files that are imported:
        release_files_by_ident = {
            (item_file.stat.st_dev, item_file.stat.st_ino): item_file
            for item_file in self.download_item.files
            if item_file.is_imported
        }
        un_imported_items: dict = {}
        for imported_item_id, imported_item in self.root_item.imported_items.items():
            if not imported_item["hasFile"]:
                continue  # pragma: no cover
            if not imported_item["file"]["path"].exists():
                logger.warning(
                    "Imported file missing: %s",
                    imported_item["file"]["path"],
                )
                continue
            imported_file_stat = imported_item["file"]["path"].stat()
            imported_file_ident = (imported_file_stat.st_dev, imported_file_stat.st_ino)
            if imported_file_ident not in release_files_by_ident:
                continue  # pragma: no cover
            un_imported_items[imported_item_id] = imported_item

        if un_imported_items:
            logger.info(
                "Removing imported files from release %r:\n  %s",
                self,
                "\n  ".join(
                    str(un_imported_item["file"]["path"])
                    for un_imported_item in un_imported_items.values()
                ),
            )
            servarr.client.delete(
                f"{servarr.type_map['item_type']}file/bulk",
                {
                    f"{servarr.type_map['item_type']}FileIds": [
                        un_imported_item["file"]["id"]
                        for un_imported_item in un_imported_items.values()
                    ]
                },
            )
            self.clear()
        else:
            logger.warning(  # pragma: no cover
                "No files to un-import from release: %r",
                self,
            )
        return un_imported_items


class PatchedStatResult(utils.PrunerrComponent):
    """
    Wrap a real ``path.stat()`` result overriding just some of the fields.
    """

    def __init__(self, original, **kwargs):
        """
        Capture references to the original result and the fields to override.
        """
        self.original = original
        vars(self).update(kwargs)

    def __getattr__(self, name):
        """
        Fallback to the real field value when it hasn't been overridden.
        """
        return getattr(self.original, name)

    @property
    def details(self) -> dict:
        """
        Assemble all available useful information.

        :return: Map descriptive names to useful values.
        """
        return {
            attr: value for attr, value in vars(self).items() if attr.startswith("st_")
        }
