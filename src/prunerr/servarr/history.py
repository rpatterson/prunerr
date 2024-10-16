# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Prunerr's view of Servarr history for a root item, for example a series or movie.
"""


import logging

from .. import utils

logger = logging.getLogger(__name__)


class PrunerrServarrHistory(utils.PrunerrComponent):
    """
    Prunerr's view of Servarr history for a root item, for example a series or movie.
    """

    imported_ids: dict
    download_ids: dict
    imported_items: dict

    def __init__(self, root_item):
        """
        Capture references to the servarr root item instance.
        """
        self.root_item = root_item
        self.dropped_relatives = {}

    @property
    def details(self) -> dict:
        """
        Assemble all available useful information.

        :return: Map descriptive names to useful values.
        """
        return self.root_item.details

    def update(self):
        """
        Map grab and import history records to download items by various means.

        There are several workflows for importing files from download items and thus
        several edge cases. The normal workflow is that Servarr grabs a release and then
        imports all files available in the grabbed download item once finished. In that
        case the download item hash ID can be determined explicitly because the grab
        history immediately precedes the import history and both history records have
        the same download item hash ID. But sometimes a finished download item requires
        manual intervention to import, in which case more files may be imported than the
        grab history expects and as such those "extra" imported files have no
        corresponding grab history but the import history may still have a download item
        ID/hash. Other times, more files may be manually imported by the user *after*
        Servarr already imported the files it expected to find from the grab history, in
        which case not only do thise "extra" imported files have no corresponding grab
        history but the import history may not have any download item hash ID at
        all. Unfortunately, these edge cases other than the normal workflow are common
        enough that it would be infeasible for the user to handle them manually. Worse,
        without the download item hash ID, the only remaining way to match is to use
        download item file paths, but it's possible, however uncommon, for those to be
        shared between different download items.

        Try to automate these other edge cases as much as possible and as safely as
        possible.
        """
        self.imported_ids = {}
        self.download_ids = {}
        self.dropped_relatives = {}

        # Re-map imported items for lookup by relative path instead of by episode/movie
        # DB ID:
        self.imported_items = {
            imported_item["id"]: imported_item
            for imported_item in self.root_item.imported_items.values()
        }

        # The Servarr API history can be large. Take an initial pass through the history
        # gathering only what we need and discarding the rest:
        for history_record in self.root_item.servarr.client.get(
            f"history/{self.root_item.servarr.type_map['dir_type']}",
            **self.root_item.params,
        ):
            if (
                history_record["eventType"]
                == self.root_item.servarr.EVENT_TYPE_IMPORTED
            ):
                self.root_item.servarr.deserialize_import_record(history_record)
                self.update_import_record(history_record)

            elif (
                history_record["eventType"] == self.root_item.servarr.EVENT_TYPE_GRABBED
            ):
                self.root_item.servarr.deserialize_grab_record(history_record)
                self.update_grab_record(history_record)

            else:
                # Not an import or grab record, skip it:
                continue  # pragma: no cover

    def update_import_record(self, history_record: dict):
        """
        Map one import history record to it's download item by various means.

        :param history_record: The Servarr API JSON object for one import history
            record.
        """
        type_map = self.root_item.servarr.type_map
        imported_id = history_record[f"{type_map['item_type']}Id"]
        # Match on relative paths to tolerate items imported before Servarr renamed the
        # top-level series/movie:
        imported_collated = {}

        if history_record["data"].get("droppedRel"):
            imported_collated["droppedRel"] = history_record["data"]["droppedRel"]
            imported_collated["location"] = history_record["data"][
                "droppedPath"
            ].parents[len(history_record["data"]["droppedRel"].parts) - 1]

        if history_record.get("downloadId"):
            # The most common case, map an imported path to a download item hash ID:
            imported_collated["downloadId"] = history_record["downloadId"]
            # Also map the download item hash ID to collated data:
            download_id_collated = self.download_ids.setdefault(
                history_record["downloadId"],
                {},
            )

            # As a last resort, match the download item's root basename to a download
            # item ID/hash:
            if dropped_relative := history_record["data"].get("droppedRel"):
                # Assume the older download item root basename is correct for the hash
                # ID, overwrite any previous values:
                if (
                    download_id_collated.get("droppedRootName")
                    and dropped_relative.parts[0]
                    != download_id_collated["droppedRootName"]
                ):
                    # Corrupt Servarr release history where the same download item hash
                    # ID is on the import history records from different download
                    # items. The only cases of this I've seen are when more recent
                    # manual imports seem to get the download item hash ID from the
                    # previous automated import they upgrade, so assume the older record
                    # is the correct download item hash ID:
                    logger.warning(
                        "Duplicate hash IDs for dropped path, choosing older: %r -> %r",
                        download_id_collated["droppedRootName"],
                        str(dropped_relative.parts[0]),
                    )
                    # When collating the older import history with the correct download
                    # item hash ID, remove the wrong download item hash ID from the data
                    # collated previously from the newer import history:
                    for old_imported_id in download_id_collated.get(
                        f"{type_map['item_type']}Id",
                        [],
                    ):
                        old_imported_collated = self.imported_ids.get(
                            old_imported_id,
                            {},
                        )
                        old_imported_collated.pop("downloadId", None)
                        if old_imported_collated.get("droppedRel"):
                            self.dropped_relatives[
                                old_imported_collated["droppedRel"]
                            ].pop("downloadId", None)
                        else:
                            pass  # pragma: no cover
                    download_id_collated.pop(f"{type_map['item_type']}Id", None)
                # Also map the download item hash ID to the root basename for comparison
                # with older history later to identify incorrect download item hash IDs:
                download_id_collated["droppedRootName"] = dropped_relative.parts[0]

            # Earlier, when collating the newer import history with the incorrect
            # download item hash ID, store a reference so we can remove that hash ID
            # when collating the older, correct history later:
            download_id_collated.setdefault(f"{type_map['item_type']}Id", []).append(
                imported_id,
            )

        # Only store collated history for the most recent import that's in the library:
        if imported_id in self.imported_items:  # pragma: no cover
            self.imported_ids.setdefault(imported_id, imported_collated)
            dropped_collated = self.dropped_relatives.setdefault(
                history_record["data"].get("droppedRel"),
                {},
            )
            dropped_collated.setdefault(
                f"{type_map['item_type']}Id",
                imported_id,
            )
            if history_record.get("downloadId"):
                dropped_collated.setdefault("downloadId", history_record["downloadId"])

    def update_grab_record(
        self,
        history_record: dict,
    ):
        """
        Map one grab history record to it's download item by various means.

        :param history_record: The Servarr API JSON object for one grab history
            record.
        """
        # Map download item IDs/hashes to download URLs if download items need
        # to be re-added to the download client:
        self.download_ids.setdefault(history_record["downloadId"], {}).setdefault(
            "downloadUrl",
            {},
        ).setdefault(
            history_record["data"]["downloadUrl"],
            {
                "downloadClient": history_record["data"]["downloadClient"],
                "nzbInfoUrl": history_record["data"]["nzbInfoUrl"],
            },
        )
