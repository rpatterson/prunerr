# SPDX-FileCopyrightText: 2024 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Link imported files back into download items and verify, Servarr import inverse.
"""

import typing
import logging

import requests
import transmission_rpc

from ..utils import pathlib

logger = logging.getLogger(__name__)


class ExportCommandRun:
    """
    Represent the state and logic of an individual run of the ``export`` sub-command.
    """

    IMPORT_KEYS = ("sourceTitle", "downloadRootName")

    data_paths = None
    download_ids: dict
    import_names: dict

    def __init__(self, servarr):
        """
        Capture a reference to the Servarr instance.

        :param servarr: The ``prunerr.servarr.PrunerrServarrInstance`` object
            representing the specific Servarr instance.
        """
        self.servarr = servarr

    def update(self, extra_data_paths: typing.Optional[list] = None):
        """
        Process command-line arguments and collate global download items data.

        :param extra_data_paths: Additional download client paths whose immediate
            children might contain download item data.
        """
        # Command-line arguments:
        if extra_data_paths is None:
            extra_data_paths = []
        # Add the paths in the download clients that this servarr instance deals
        # with:
        data_paths = []
        for servarr_download_client in self.servarr.download_clients.values():
            data_paths.extend(
                [
                    servarr_download_client.seeding_dir,
                    servarr_download_client.download_dir,
                ]
            )
            # Add the path suffix specific to this Servarr instance to each of the extra
            # data paths:
            servarr_suffix = servarr_download_client.download_dir.relative_to(
                servarr_download_client.download_client.client.session.download_dir,
            )
            data_paths.extend(
                extra_data_path / servarr_suffix for extra_data_path in extra_data_paths
            )
        # Remove duplicates but preserve order:
        self.data_paths = list(dict.fromkeys(data_paths))

        # Collect global download item data shared between series/movies:
        self.download_ids = {}
        self.import_names = {import_key: {} for import_key in self.IMPORT_KEYS}
        for download_client in self.servarr.download_clients.values():
            for item in download_client.download_client.items:
                self.download_ids.setdefault(item.hashString.upper(), []).append(item)

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
            root_item = ExportServarrRootItem(self, servarr_root_item)
            root_item.update()
            if linked_files := root_item():
                export_results[servarr_root_item["title"]] = linked_files

        # Report results if any:
        if export_results:
            return export_results
        return None


class ExportServarrRootItem:
    """
    Represent the state and logic of exporting one Servarr series/movie/etc..
    """

    IMPORT_EVENT_TYPE = "downloadFolderImported"
    GRAB_EVENT_TYPE = "grabbed"

    imported_items: dict
    download_ids: dict
    imported_relatives: dict
    import_names: dict
    imported_download_ids: dict

    def __init__(self, command_run, root_item):
        """
        Capture references to this `export` sub-command run and Servarr series/movie.

        :param command_run: The ``ExportCommandRun`` object representing this run of the
            ``$ prunerr export`` sub-command.
        :param root_item: The dictionary from the Servarr API JSON for the top-level
            library item, for example series or movie.
        """
        self.command_run = command_run
        self.root_item = root_item

    def update(self):
        """
        Get and collate the data export requires from the Servarr API.
        """
        # First connect everything we can directly from the Servarr API:
        self.imported_items = self.collate_imported_files()
        self.update_servarr_history()

        # Next, map imported file paths missing download item IDs/hashes by further
        # methods now that all history data has been collated:
        self.lookup_download_ids()

        # Now group the imported files under the download item IDs/hashes the come from
        # them:
        self.imported_download_ids = {}
        for imported_relative in self.imported_items:
            imported_collated = self.imported_relatives.get(imported_relative, {})
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
        for download_id in self.imported_download_ids:
            # Next, ensure all download hashes are in the download client, re-adding the
            # items if necessary:
            need_verify = (
                maybe_add_download_item(
                    self.command_run.download_ids,
                    download_id,
                    self.download_ids.get(download_id, {}).get("downloadUrl", {}),
                )
                is not None
            )

        # As a last resort, map any imported paths without download item IDs by the
        # pre-existing download item names and root basenames in the client:
        for download_items in self.command_run.download_ids.values():
            for download_item in download_items:
                if not self.command_run.import_names["sourceTitle"].get(
                    download_item.name,
                ):
                    self.command_run.import_names["sourceTitle"][
                        download_item.name
                    ] = download_item.hashString
                if not self.command_run.import_names["downloadRootName"].get(
                    download_item.root_name,
                ):
                    self.command_run.import_names["downloadRootName"][
                        download_item.name
                    ] = download_item.hashString
        self.imported_download_ids.update(
            self.lookup_download_ids(
                mapped_names=self.command_run.import_names,
            ),
        )

        # Finally, hard link imported files into the download items:
        linked_files = []
        for download_id, imported_relatives in self.imported_download_ids.items():
            for download_item in self.command_run.download_ids.get(
                download_id,
                [],
            ):
                linked_files.extend(
                    download_item.link_imported_files(
                        self.command_run.data_paths,
                        pathlib.Path(self.root_item["path"]),
                        imported_relatives,
                        need_verify=need_verify,
                    ),
                )
        return linked_files

    def collate_imported_files(self) -> dict:
        """
        Map each imported item and corresponding imported file by the relative path.

        :return: Map relative paths to the Servarr API JSON object for the imported item
            annotated with the imported file object.
        """
        # Map item file IDs for correlating to the items:
        params = {
            f"{self.command_run.servarr.type_map['dir_type']}Id": self.root_item["id"],
        }
        item_files = {
            item_file["id"]: item_file
            for item_file in self.command_run.servarr.client.get(
                f"{self.command_run.servarr.type_map['item_type']}File",
                **params,
            )
        }
        # Is there a 2nd level to get to files, for example series -> episode ->
        # file as opposed to just movie -> file:
        items = (
            [self.root_item]
            if self.command_run.servarr.type_map["file_depth"] == 1
            else self.command_run.servarr.client.get(
                self.command_run.servarr.type_map["item_type"],
                **params,
            )
        )
        # Then iterate over the imported files:
        imported_items = {}
        for imported_item in items:
            if not imported_item["hasFile"] is True:
                continue
            imported_item["file"] = item_files[
                imported_item[f"{self.command_run.servarr.type_map['item_type']}FileId"]
            ]
            imported_item["file"]["path"] = pathlib.Path(
                imported_item["file"]["path"],
            )
            imported_item["file"]["relative"] = imported_item["file"][
                "path"
            ].relative_to(
                imported_item["file"]["path"].parents[
                    self.command_run.servarr.type_map["file_depth"] - 1
                ]
            )
            imported_items[imported_item["file"]["relative"]] = imported_item
        return imported_items

    def update_servarr_history(self):
        """
        Map grab and import history records to download items by various means.

        There are several workflows for importing files from download items and thus
        several edge cases. The normal workflow is that Servarr grabs a release and then
        imports all files available in the grabbed download item once finished. In that
        case the download item ID/hash can be determined explicitly because the grab
        history immediately precedes the import history and both history records have
        the same download item ID/hash. But sometimes a finished download item requires
        manual intervention to import, in which case more files may be imported than the
        grab history expects and as such those "extra" imported files have no
        corresponding grab history but the import history may still have a download item
        ID/hash. Other times, more files may be manually imported by the user *after*
        Servarr already imported the files it expected to find from the grab history, in
        which case not only do thise "extra" imported files have no corresponding grab
        history but the import history may not have any download item ID/hash at
        all. Unfortunately, these edge cases other than the normal workflow are common
        enough that it would be infeasible for the user to handle them manually. Worse,
        without the download item ID/hash, the only remaining way to match is to use
        download item names or file paths, but it's possible, however uncommon, for
        those to be shared between different download items.

        To automate these other edge cases as much as possible and as safely as
        possible, try to match imported files to download items using several
        methods. These methods are tried in order and no further method are tried once a
        method yields a download item ID/hash for a given imported file:

        #. First, if the import history has a download item ID/hash, then it is matched
           by that.

        #. Next, if the import history has a download item name and the grab history for
           the whole series/movie has that same download item name, then use the
           download item ID/hash from that grab history.

        #. Use known paths where Servarr imports download item files from to determine
           the root basename common to all files in the download item. If the grab
           history for the whole series/movie has a download item name that matches that
           root basename, then use the download item ID/hash from that grab history.

        #. Finally, use the root basename from the previous method to determine the
           relative path within the download item's files for this imported file. Match
           that relative path to the relative paths for all download items' files in the
           download client's items and use the newest matching download item's ID/hash.

        Note that matching by the relative paths of download item files requires those
        download items to be currently added in the download client. This means the last
        method, matching by file relative paths, can't be done until the grab history
        from the previous methods have been used to re-add all download items not still
        in the download client. This also means, that if a download item has been
        removed from the download client and none of the previous methods yield grab
        history for a download item, then the last relative path method can't make a
        match at all.
        """
        self.imported_relatives = {}
        self.download_ids = {}
        self.import_names = {
            import_key: {} for import_key in self.command_run.IMPORT_KEYS
        }
        for history_record in self.command_run.servarr.client.get(
            f"history/{self.command_run.servarr.type_map['dir_type']}",
            **{
                f"{self.command_run.servarr.type_map['dir_type']}Id": self.root_item[
                    "id"
                ],
            },
        ):
            if history_record["eventType"] == self.IMPORT_EVENT_TYPE:
                # Use relative paths to tolerate items imported before Servarr renamed
                # the top-level series/movie:
                imported_path = pathlib.Path(history_record["data"]["importedPath"])
                imported_relative = imported_path.relative_to(
                    imported_path.parents[
                        self.command_run.servarr.type_map["file_depth"] - 1
                    ],
                )
                self.update_import_record(history_record, imported_relative)

            elif history_record["eventType"] == self.GRAB_EVENT_TYPE:
                self.update_grab_record(history_record)

            else:  # pragma: no cover
                # Not an import or grab record, skip it:
                continue

            # If the import history has no download item ID/hash, try to match on the
            # download item name in `sourceTitle`:
            if history_record.get("sourceTitle") and history_record.get("downloadId"):
                self.import_names["sourceTitle"].setdefault(
                    history_record["sourceTitle"],
                    history_record["downloadId"],
                )

    def update_import_record(
        self,
        history_record: dict,
        imported_relative: pathlib.Path,
    ):
        """
        Map one import history record to it's download item by various means.

        :param history_record: The Servarr API JSON object for one import history
            record.
        :param imported_relative: The relative path to the imported file within the
            series/movie.
        """
        # Match on relative paths to tolerate items imported before Servarr renamed the
        # top-level series/movie:
        imported_collated = {}

        # Determine which part of the paths are from the download item:
        dropped_path = pathlib.Path(history_record["data"]["droppedPath"])
        download_root_name = None
        for data_path in self.command_run.data_paths:
            if data_path.resolve() in dropped_path.resolve().parents:
                dropped_relative = dropped_path.resolve().relative_to(data_path)
                imported_collated["droppedRel"] = dropped_relative
                imported_collated["location"] = dropped_path.parents[
                    len(dropped_relative.parts) - 1
                ]
                download_root_name = imported_collated["downloadRootName"] = (
                    dropped_relative.parts[0]
                )
                break
        else:
            logger.error(
                "No download root name found: %s",
                dropped_path,
            )

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
            if download_root_name:
                # Assume the older download item root basename is correct for the hash
                # ID, overwrite any previous values:
                self.import_names["downloadRootName"][download_root_name] = (
                    history_record["downloadId"]
                )
                if (
                    download_id_collated.get("downloadRootName")
                    and download_root_name != download_id_collated["downloadRootName"]
                ):  # pragma: no cover
                    # Corrupt Servarr download item history where the same download item
                    # hash ID is on the import history records from different download
                    # items. The only cases of this I've seen are when more recent
                    # manual imports seem to get the download item hash ID from the
                    # previous automated import they upgrade, so assume the older record
                    # is the correct download item hash ID:
                    logger.error(
                        "Duplicate"
                        " hash IDs for root basename, choosing older"
                        ": %r -> %r",
                        download_id_collated["downloadRootName"],
                        download_root_name,
                    )
                    # When collating the older import history with the correct download
                    # item hash ID, remove the wrong download item hash ID from the data
                    # collated previously from the newer import history:
                    for old_imported_relative in download_id_collated.get(
                        "importedRel",
                        [],
                    ):
                        old_imported_collated = self.imported_relatives.get(
                            old_imported_relative,
                            {},
                        )
                        old_imported_collated.pop("downloadId", None)
                        old_imported_collated.pop("sourceTitle", None)
                    download_id_collated.pop("importedRel", None)
                # Also map the download item hash ID to the root basename for comparison
                # with older history later to identify incorrect download item hash IDs:
                download_id_collated["downloadRootName"] = download_root_name

            # Earlier, when collating the newer import history with the incorrect
            # download item hash ID, store a reference so we can remove that hash ID
            # when collating the older, correct history later:
            download_id_collated.setdefault("importedRel", []).append(imported_relative)

        # If the import history has no download item ID/hash, try to match on
        # the download item name in `sourceTitle`:
        if history_record.get("sourceTitle"):  # pragma: no cover
            imported_collated["sourceTitle"] = history_record["sourceTitle"]

        # Only store collated history for the most recent import that's in the library:
        if imported_relative in self.imported_items:  # pragma: no cover
            self.imported_relatives.setdefault(imported_relative, imported_collated)

    def update_grab_record(
        self,
        history_record: dict,
    ):
        """
        Map one grab history record to it's download item by various means.

        :param history_record: The Servarr API JSON object for one grab history
            record.
        """
        # Match this grab history to it's download client:
        if (
            history_record["data"]["downloadClientName"]
            in self.command_run.servarr.download_client_names
        ):
            download_client = self.command_run.servarr.download_client_names[
                history_record["data"]["downloadClientName"]
            ]
        else:  # pragma: no cover
            logger.warning(
                "Download client name not found, defaulting to first: %s",
                history_record["data"]["downloadClientName"],
            )
            download_client = list(
                self.command_run.servarr.download_client_names.values(),
            )[0]

        # Map download item IDs/hashes to download URLs if download items need
        # to be re-added to the download client:
        self.download_ids.setdefault(history_record["downloadId"], {}).setdefault(
            "downloadUrl",
            {},
        ).setdefault(
            history_record["data"]["downloadUrl"],
            {
                "downloadClient": download_client,
                "nzbInfoUrl": history_record["data"]["nzbInfoUrl"],
            },
        )

    def lookup_download_ids(
        self,
        mapped_names: typing.Optional[dict] = None,
    ) -> dict:
        """
        Lookup the download IDs for imported files without them by download item name.

        :param mapped_names: Map download items by hashes, names and root basenames
            (default: ``self.import_names``).
        :return: Map download item names and root basenames to download item hash IDs.
        """
        if mapped_names is None:
            mapped_names = self.import_names
        download_ids: dict = {}
        download_ids_by_names: dict = {}
        for imported_relative, imported_item in self.imported_items.items():
            download_id = self.imported_relatives.get(
                imported_relative,
                {},
            ).get("downloadId")
            if download_id:
                continue

            download_id = self.lookup_download_id(
                mapped_names,
                download_ids_by_names,
                imported_relative,
                imported_item,
            )
            if download_id:
                download_ids.setdefault(download_id, {}).setdefault(
                    imported_relative,
                    self.imported_relatives.get(imported_relative, {}),
                )
                self.imported_relatives[imported_relative].setdefault(
                    "downloadId",
                    download_id,
                )

        return download_ids

    def lookup_download_id(
        self,
        mapped_names: dict,
        download_ids_by_names: dict,
        imported_relative: pathlib.Path,
        imported_item: dict,
    ) -> typing.Optional[str]:
        """
        Lookup the download IDs for imported files without them by download item name.

        :param mapped_names: Map download items by hashes, names and root basenames.
        :param download_ids_by_names: Map import names and root basenames to download
            item hash IDs.
        :param imported_relative: The relative path to the imported file within the
            series/movie.
        :param imported_item: The Servarr API JSON object for the imported item
            annotated with the imported file object.
        :return: The download item hash ID if one matched by name or root basename.
        """
        imported_collated = self.imported_relatives.get(imported_relative, {})
        for import_key in self.command_run.IMPORT_KEYS:
            if not (
                import_name := imported_collated.get(import_key)
            ):  # pragma: no cover
                continue

            if download_id := download_ids_by_names.get(import_key, {}).get(
                import_name
            ):  # pragma: no cover
                logger.debug(
                    "Reusing previous download item %r name lookup, %r: %s",
                    import_key,
                    import_name,
                    imported_item["file"]["path"],
                )
            elif download_id := lookup_import_name(
                mapped_names,
                import_key,
                import_name,
            ):
                pass
            else:
                # As a last resort cross the import keys to make inexact
                # matches. For example, manual import records whose `sourceTitle` is
                # not the download item's name may still match to the `sourceTitle`
                # by `downloadRootname` for the vast majority of download items
                # where those two are the same:
                for cross_import_key in self.command_run.IMPORT_KEYS:
                    if cross_import_key == import_key:
                        continue
                    download_id = lookup_import_name(
                        mapped_names,
                        cross_import_key,
                        import_name,
                    )

            if download_id:
                download_ids_by_names.setdefault(import_key, {}).setdefault(
                    import_name,
                    download_id,
                )
                return download_id

        logger.error(
            "Could not lookup download item by names: %s",
            imported_item["file"]["path"],
        )
        return None


def lookup_import_name(
    mapped_names: dict,
    import_key: str,
    import_name: str,
) -> typing.Optional[str]:
    """
    Lookup one download item ID by a given import data key and corresponding name.

    :param mapped_names: Map download items by hashes, names and root basenames.
    :param import_key: The key in the Servarr API JSON for history to match the name
        with.
    :param import_name: The download item name or root basename to match.
    :return: The download item hash ID if one matched.
    """
    if not (download_id := mapped_names[import_key].get(import_name)):
        return None
    logger.info(
        "Matched download item by %r name: %s",
        import_key,
        import_name,
    )
    return download_id


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
            download_items_by_id[download_id][0].name,
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
            download_item = download_data["downloadClient"].download_client.add_torrent(
                download_url,
                paused=True,
                download_dir=str(download_data["downloadClient"].seeding_dir),
            )
        except (
            requests.exceptions.RequestException,
            transmission_rpc.error.TransmissionError,
        ):  # pragma: no cover
            # Tolerate exceptions adding torrents because the download
            # URL may no longer be valid, IOW 404:
            logger.exception(
                "Exception adding torrent: %s",
                download_data.get("nzbInfoUrl") or download_url,
            )
            continue
        else:
            download_items_by_id.setdefault(
                download_item.hashString.upper(),
                [],
            ).append(download_item)
            return download_item

    return None  # pragma: no cover
