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
        return {
            "servarr": self.servarr_download_client.servarr.config.get("name"),
            "dowload_client": self.servarr_download_client.config.get("url"),
            "torrent": self.download_item,
        }

    @cached_property
    def queue(self) -> dict:
        """
        Lookup this release's queue record from it's Servarr instance.

        :return: The Servarr API ``queue`` endpoint JSON for this release.
        """
        return self.servarr_download_client.servarr.queue.get(
            self.download_item.hashString.upper(),
        )

    @cached_property
    def history(self) -> list:
        """
        Lookup and collate this download item's Servarr history records.

        :return: The Servarr API ``history`` endpoint JSON for this release.
        """
        return list(
            self.servarr_download_client.servarr.get_api_paged_records(
                "history",
                downloadId=self.download_item.hashString.upper(),
            ),
        )

    @cached_property
    def root_item(self) -> typing.Optional[rootitem.PrunerrServarrRootItem]:
        """
        Lookup the Servarr series/movie corresponding to this release if any.

        :return: The Prunerr root item instance.
        """
        root_id = None
        servarr = self.servarr_download_client.servarr
        for queue_record in self.queue:
            if root_id is None:
                root_id = queue_record[f"{servarr.type_map['dir_type']}Id"]
            elif queue_record[f"{servarr.type_map['dir_type']}Id"] != root_id:
                logger.error(
                    "Release queued for more than one Servarr root item: %r",
                    self,
                )
                break
        if root_id is not None:
            return servarr.get_root_item(root_id)
        return None

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
        raise NotImplementedError(
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
        raise NotImplementedError(
            "Cannot simulate upgrade outside the ``upgraded`` life-cycle stage"
            f": {self!r}",
        )

    def filter_upgraded(self) -> collections.abc.Generator:
        """
        Identify the releases this release will upgrade when imported.

        :return: The ``prunerr.downloaditem.PrunerrDownloadItem()`` instances.
        :raises ValueError: There's a problem identifying which items this item will
            upgrade.
        """
        if self.root_item is None:
            raise ValueError(
                "Cannot review a release not connected to its root item: {self!r}",
            )

        # This is sort of a many-to-many issue. A queued release may upgrade multiple
        # imported releases, such as a season pack queued release upgrading individual
        # episode imported releases. Conversely, a `WEB-DL` season pack imported release
        # may be upgraded by multiple `Bluray` single episode queued releases. So
        # collate the required data for *this* queued release but in such a way that it
        # can be supplemented by other queued releases.

        # First group the imported files that will be upgraded by the currently imported
        # releases they were imported from:
        imported_by_release: dict = {}
        servarr = self.servarr_download_client.servarr
        for queue_record in self.queue:
            imported_item_id = queue_record[f"{servarr.type_map['item_type']}Id"]
            if not queue_record[f"{servarr.type_map['item_type']}HasFile"]:
                # This episode/movie is not currently imported, there is no release that
                # will be upgraded when this queued release is imported:
                logger.debug(
                    "No imported file %r for queued release %r: %s",
                    imported_item_id,
                    queue_record["title"],
                    queue_record["downloadId"],
                )
                continue
            imported_release = self.root_item.imported_releases.get(imported_item_id)
            if imported_release is not None:
                imported_by_release.setdefault(
                    imported_release.download_item.hashString,
                    (imported_release, {}),
                )[1].setdefault(
                    self.root_item.imported_items[imported_item_id]["file"]["relative"],
                    None,
                )

        # Now use the grouped imported files to simulate the state of the imported item
        # after it has been upgraded by importing the queued release and review it:
        for imported_release, imported_relatives in imported_by_release.values():

            # Share one simulated upgraded release for all the queued releases that will
            # upgrade it:
            if imported_release.UPGRADED_RELEASE_ATTR not in vars(imported_release):
                imported_release.upgraded_release = type(imported_release)(
                    imported_release.servarr_download_client,
                    type(imported_release.download_item)(
                        imported_release.download_item.download_client,
                        imported_release.download_item.download_client.client,
                        imported_release.download_item,
                    ),
                )
            if self.QUEUED_UPGRADES_ATTR not in vars(imported_release):
                imported_release.queued_upgrades = {}
            imported_release.queued_upgrades.setdefault(
                self.download_item.hashString.upper(),
                self,
            )

            # Map the imported release's files to the queued releases that will upgrade
            # them:
            for imported_relative in imported_relatives:
                dropped_relative = self.root_item.history.imported_relatives[
                    imported_relative
                ]["droppedRel"]
                item_file = imported_release.download_item.files_by_relative[
                    dropped_relative
                ]
                if self.QUEUED_UPGRADES_ATTR not in vars(item_file):
                    item_file.queued_upgrades = {}
                item_file.queued_upgrades.setdefault(
                    self.download_item.hashString.upper(),
                    self,
                )

                # Decrement the hard link count for all the files of the imported
                # release that will be upgraded by this queued release and replace the
                # cached `item_file.stat()` results:
                imported_release.upgraded_release.download_item.files_by_relative[
                    dropped_relative
                ].stat = PatchedStatResult(
                    item_file.stat,
                    st_nlink=item_file.stat.st_nlink - 1,
                )

            yield imported_release.download_item


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
