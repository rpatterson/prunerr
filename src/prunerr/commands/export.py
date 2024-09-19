# SPDX-FileCopyrightText: 2024 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Link imported files back into download items and verify, Servarr import inverse.
"""

import typing
import logging

import requests
import transmission_rpc

import prunerr.servarr.rootitem
from ..utils import pathlib

logger = logging.getLogger(__name__)


class ExportCommandRun:
    """
    Represent the state and logic of an individual run of the ``export`` sub-command.
    """

    download_ids: dict

    def __init__(self, servarr):
        """
        Capture a reference to the Servarr instance.

        :param servarr: The ``prunerr.servarr.PrunerrServarrInstance`` object
            representing the specific Servarr instance.
        """
        self.servarr = servarr

    def update(self):
        """
        Process command-line arguments and collate global download items data.
        """
        # Collect global download item data shared between series/movies:
        self.download_ids = {}
        for servarr_download_client in self.servarr.download_clients.values():
            for release in servarr_download_client.releases:
                self.download_ids.setdefault(
                    release.download_item.hashString.upper(),
                    [],
                ).append(release)

    def __call__(self) -> typing.Optional[dict]:
        """
        Link imported files back into download items and verify, Servarr import inverse.

        #. Get the latest import and grab history records for every currently imported
           file in the library.

        #. Collect the unique download item IDs from all the grab records.

        #. Ensure that the download client currently has the download item for each
           download item ID, re-adding the item paused if necessary.

        #. For import records that have no grab records, such as manual imports, get
           their download item IDs by matching on download item name.

        #. Locate existing download item data in known directories and set the most
           recently modified as the download item's location.

        #. For each imported file, ensure it's hard-linked into the download client for
           every download client that has that download item.

        #. Deselect for download any remaining incomplete files.

        #. Verify and resume the download item.

        :return: Map series/movies to the relative paths of any imported files that were
            linked into the download item.
        """
        # Start with collated grab and import history for each series/movie:
        export_results = {}
        for servarr_root_item in self.servarr.client.get(
            self.servarr.type_map["dir_type"],
        ):
            export_root_item = ExportServarrRootItem(
                self,
                prunerr.servarr.rootitem.PrunerrServarrRootItem(
                    self.servarr,
                    servarr_root_item["id"],
                ),
            )
            export_root_item.update(servarr_root_item)
            if linked_files := export_root_item():
                export_results[servarr_root_item["title"]] = linked_files

        # Report results if any:
        if export_results:
            return export_results
        return None


class ExportServarrRootItem:
    """
    Represent the state and logic of exporting one Servarr series/movie/etc..
    """

    imported_download_ids: dict

    def __init__(
        self,
        command_run,
        root_item: "prunerr.servarr.rootitem.PrunerrServarrRootItem",
    ):
        """
        Capture references to this `export` sub-command run and Servarr series/movie.

        :param command_run: The ``ExportCommandRun`` object representing this run of the
            ``$ prunerr export`` sub-command.
        :param root_item: The Prunerr representation a root Servarr item, for example a
            series or movie.
        """
        self.command_run = command_run
        self.root_item = root_item

    def update(self, data: dict):
        """
        Get and collate the data export requires from the Servarr API.

        :param data: The dictionary from the Servarr API JSON for the top-level
            library item, for example series or movie.
        """
        # Assemble the series/movie data that is different for `export` from `apply`:
        self.root_item.data = data

        # Now group the imported files under the download item IDs/hashes the come from
        # them:
        self.imported_download_ids = {}
        for imported_relative in self.root_item.history.imported_items:
            imported_collated = self.root_item.history.imported_relatives.get(
                imported_relative, {}
            )
            if not (
                imported_collated.get("downloadId")
                and imported_collated.get("droppedRel")
            ):
                # Logged in `lookup_download_ids()`:
                continue
            self.imported_download_ids.setdefault(
                imported_collated["downloadId"],
                {},
            ).setdefault(imported_relative, imported_collated)

    def __call__(self):
        """
        Link imported files back into download items for one series/movie.

        :param mapped_download_items: Map download items by hashes, names and root
            basenames.
        :return: The download item file paths of any imported files that were linked
            into the download item.
        """
        # Add download items to the client now that we've done everything we can to
        # identify any download items that aren't already in the client:
        added_items = {}
        for download_id in self.imported_download_ids:
            # Next, ensure all download hashes are in the download client, re-adding the
            # items if necessary:
            added_item = maybe_add_download_item(
                self.command_run.download_ids,
                download_id,
                self.root_item.history.download_ids.get(download_id, {}).get(
                    "downloadUrl", {}
                ),
            )
            if added_item is not None:
                added_items[added_item.hashString] = added_item

        # As a last resort, map any imported paths without download item IDs by the
        # pre-existing download item names and root basenames in the client:
        for releases in self.command_run.download_ids.values():
            for release in releases:
                for download_file in release.download_item.files:
                    if (
                        download_file.relative
                        in self.root_item.history.dropped_relatives
                        and not self.root_item.history.dropped_relatives[
                            download_file.relative
                        ]
                    ):
                        self.root_item.history.dropped_relatives[
                            download_file.relative
                        ] = release.download_item.hashString.upper()
        for (
            download_id,
            imported_relatives,
        ) in self.root_item.history.lookup_download_ids().items():
            self.imported_download_ids.setdefault(download_id, {}).update(
                imported_relatives,
            )

        # Finally, hard link imported files into the download items:
        linked_files = []
        for download_id, imported_relatives in self.imported_download_ids.items():
            for release in self.command_run.download_ids.get(
                download_id,
                [],
            ):
                item_root_paths = list(
                    release.download_item.download_client.download_dir.parent.glob(
                        f"*/{release.servarr_download_client.download_dir_suffix}"
                        f"/{release.download_item.root_name}",
                    ),
                )
                linked_files.extend(
                    release.download_item.link_imported_files(
                        item_root_paths,
                        pathlib.Path(self.root_item.data["path"]),
                        imported_relatives,
                        need_verify=download_id.lower() in added_items,
                    ),
                )
        return linked_files


def maybe_add_download_item(
    download_items_by_id: dict,
    download_id: str,
    download_urls: dict,
) -> transmission_rpc.Torrent:
    """
    Add a download item from the given URL if not already in the download client.

    :param download_items_by_id: Map download item hashes to the items.
    :param download_id: The download item hash ID.
    :param download_urls: The download item URLs mapped to the download client to add
        them to.
    :return: The download item whether added or existing or None if it could not be
        added.
    """
    if download_id in download_items_by_id:
        logger.debug(
            "Skipping already added torrent: %s",
            download_items_by_id[download_id][0].download_item.name,
        )
        return None
    if not download_urls:  # pragma: no cover
        logger.error(
            "No grab history found for download item ID/hash: %s",
            download_id,
        )
        return None

    # Try each download URL from the grab history, most recent first:
    for download_url, download_data in download_urls.items():
        try:
            release = download_data["downloadClient"].add_torrent(
                download_url,
                paused=True,
                download_dir=str(download_data["downloadClient"].seeding_dir),
            )
        except (  # pragma: no cover
            requests.exceptions.RequestException,
            transmission_rpc.error.TransmissionError,
        ):
            # Tolerate exceptions adding torrents because the download
            # URL may no longer be valid, IOW 404:
            logger.exception(
                "Exception adding torrent: %s",
                download_data.get("nzbInfoUrl") or download_url,
            )
            continue
        else:
            download_items_by_id.setdefault(
                release.download_item.hashString.upper(),
                [],
            ).append(release)
            return release.download_item

    return None  # pragma: no cover
