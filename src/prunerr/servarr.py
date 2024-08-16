# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

# pylint: disable=magic-value-comparison,missing-any-param-doc,missing-param-doc
# pylint: disable=missing-raises-doc,missing-return-doc,missing-return-type-doc
# pylint: disable=missing-type-doc,missing-yield-doc,missing-yield-type-doc

"""
Prunerr interaction with Servarr instances.
"""

import dataclasses
import time
import urllib.parse
import typing
import logging

import requests
import transmission_rpc
import arrapi
import arrapi.apis.base

import prunerr.downloadclient
import prunerr.downloaditem
from . import utils
from .utils import pathlib

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PrunerrServarrAPIClient:
    """
    Wrap the `arrapi` client private/internal bits we depend on.
    """

    client: arrapi.apis.base.BaseAPI

    @property
    def get(self):
        """
        Return the `arrapi` client private/internal `GET` method.
        """
        return self.client._raw._get  # pylint: disable=protected-access

    @property
    def delete(self):
        """
        Return the `arrapi` client private/internal `DELETE` method.
        """
        return self.client._raw._delete  # pylint: disable=protected-access


class PrunerrServarrInstance:
    """
    An individual, specific Servarr instance that Prunerr interacts with.
    """

    # Map the different Servarr applications type terminology
    TYPE_MAPS = {
        "sonarr": {
            # The top-level containing type, if applicable.  IOW, the type of items in
            # the top-level listing of the Servarr UI.  This is series for Sonarr as
            # contrasted with episode or season.  This is movie for Radarr.
            "dir_type": "series",
            # File vs item is a little confusing.  Item refers to episodes/movies as
            # contrasted with the `dir_type`.  But an episode/movie may comprise of
            # multiple files and a file may contain multiple episodes.
            "item_type": "episode",
            "client": arrapi.SonarrAPI,
            "download_dir_field": "tvDirectory",
            "rename_template": (
                "{series[title]} - {episode[seasonEpisode]} - {episode[title]}"
            ),
            "file_depth": 2,
            "item_history_is_typed": False,
            "item_history_is_paged": True,
        },
        "radarr": {
            "dir_type": "movie",
            "item_type": "movie",
            "client": arrapi.RadarrAPI,
            "download_dir_field": "movieDirectory",
            "rename_template": "{movie[title]} ({movie[release_year]})",
            "file_depth": 1,
            "item_history_is_typed": True,
            "item_history_is_paged": False,
        },
    }
    MAX_PAGE_SIZE = 250

    queue = None

    def __init__(self, runner):
        """
        Capture a references to the runner and individual Servarr configuration.
        """
        self.runner = runner
        self.type_map = None
        self.config = {}
        self.client = None
        self.download_clients = {}
        self.download_client_names = {}

    def __repr__(self):
        """
        Readable, informative, and specific representation to ease debugging.
        """
        return f"<{type(self).__name__} {self.config.get('name')!r}>"

    def update(self, config):
        """
        Update configuration, connect the API client, and refresh Servarr API data.

        Also retrieves any download clients defined in the Servarr settings and updates
        the prunerr representations.
        """
        self.config = config
        self.config["url"] = utils.normalize_url(self.config["url"])
        self.type_map = self.TYPE_MAPS[self.config["type"]]

        logger.debug(
            "Connecting to %s",
            self.config["name"],
        )
        self.client = PrunerrServarrAPIClient(
            self.type_map["client"](
                self.config["url"],
                self.config["api-key"],
            ),
        )

        download_clients = {}
        download_client_names = {}
        logger.debug(
            "Requesting %s download clients settings",
            self.config["name"],
        )
        for servarr_download_client in self.client.get("downloadclient"):
            if (
                not servarr_download_client["enable"]
                or servarr_download_client["implementation"] != "Transmission"
            ):  # pragma: no cover
                # BBB: Why misidentified as not covered under Python 3.9?
                continue
            download_client_config = deserialize_servarr_download_client(
                servarr_download_client,
            )
            # Instantiate newly defined download clients
            download_client_url = utils.normalize_url(download_client_config["url"])
            download_clients[download_client_url] = PrunerrServarrDownloadClient(self)
            download_clients[download_client_url].update(download_client_config)
            download_client_names[servarr_download_client["name"]] = download_clients[
                download_client_url
            ]
        self.download_clients = download_clients
        self.download_client_names = download_client_names

        # Update any data in instance state that should *not* be cached across updates
        self.queue = {
            record["downloadId"]: dict(record, servarr=self)
            for record in self.get_api_paged_records("queue")
            # `Pending` records have no download client hash yet
            if record.get("downloadId")
        }

        return self.client

    def export(  # noqa: MC0001, pylint: disable=too-complex
        self,
        extra_data_paths=None,
    ) -> typing.Optional[dict]:
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

        :param extra_data_paths: Additional download client paths whose immediate
            children might contain download item data.
        :return: Map series/movies to the relative paths of any imported files that were
            linked into the download item.
        """
        data_paths = self.collect_data_paths(extra_data_paths)
        download_items_by_id: dict = {}
        download_ids_by_name: dict = {"sourceTitle": {}, "downloadRootName": {}}
        for download_client in self.download_clients.values():
            for item in download_client.download_client.items:
                download_items_by_id.setdefault(item.hashString.upper(), []).append(
                    item,
                )
                download_ids_by_name["sourceTitle"].setdefault(
                    item.name,
                    item.hashString.upper(),
                )
                download_ids_by_name["downloadRootName"].setdefault(
                    item.root_name,
                    item.hashString.upper(),
                )

        # Start with collated grab and import history for each series/movie:
        export_results = {}
        for root_item in self.client.get(self.type_map["dir_type"]):
            linked_files = self.export_root_item(
                data_paths,
                download_items_by_id,
                download_ids_by_name,
                root_item,
            )
            if linked_files:
                export_results[root_item["title"]] = linked_files

        # Report results if any:
        if export_results:
            return export_results
        return None

    def export_root_item(
        self,
        data_paths,
        download_items_by_id,
        download_ids_by_name,
        root_item,
    ):
        """
        Link imported files back into download items for one series/movie.

        :param data_paths: The full list of data paths including those from the Servarr
            download clients.
        :param download_items_by_id: Map download item hashes to the items.
        :param download_ids_by_name: Map download item root basenames to the items.
        :param root_item: The dictionary from the Servarr API JSON for the top-level
            library item, for example series or movie.
        :return: The download item file paths of any imported files that were linked
            into the download item.
        """
        mapped_history = self.collate_export_history(data_paths, root_item)

        # Map imported file paths missing download item IDs/hashes by further methods
        # now that all history data has been collated:
        imported_items = list(self.list_imported_files(root_item))
        lookup_download_ids(download_ids_by_name, mapped_history, imported_items)

        # Now group the imported files under the download item IDs/hashes the come from
        # them:
        download_ids = {}
        for imported_item in imported_items:
            imported_collated = mapped_history["importedRel"].get(
                imported_item["file"]["relative"],
                {},
            )
            download_id = imported_collated.get("downloadId")
            if not (
                imported_collated.get("downloadId")
                and imported_collated.get("droppedRel")
            ):
                # Logged in `lookup_download_ids()`:
                continue
            download_ids.setdefault(imported_collated["downloadId"], {}).setdefault(
                imported_item["file"]["relative"],
                imported_collated,
            )

        linked_files = []
        for download_id, imported_relatives in download_ids.items():
            # Next, ensure all download hashes are in the download client, re-adding the
            # items if necessary:
            need_verify = (
                maybe_add_download_item(
                    download_items_by_id,
                    download_ids_by_name,
                    download_id,
                    mapped_history["downloadId"].get(download_id, {}),
                )
                is not None
            )

            # Finally, hard link imported files into the download items:
            for download_item in download_items_by_id.get(download_id, []):
                linked_files.extend(
                    download_item.link_imported_files(
                        data_paths,
                        pathlib.Path(root_item["path"]),
                        imported_relatives,
                        need_verify=need_verify,
                    ),
                )
        return linked_files

    def get_api_paged_records(self, endpoint, page_number=1, **params):
        """
        Yield each page of the given paged endpoint until exhausted.

        Useful to continue only as far as needed in a large data set, such as Servarr
        history, but also useful to conveniently get all pages of a smaller data set.
        """
        response = {}
        while (  # pylint: disable=while-used
            # First page, no response yet
            not response
            # Are the pages for this endpoint on this Servarr instance exhausted?
            or (page_number * response["pageSize"]) <= response["totalRecords"]
        ):
            logger.debug(
                "Requesting %s %r page %s with params: %r",
                self.config["name"],
                endpoint,
                page_number,
                params,
            )
            # Default to the global maximum Servarr page size:
            params.setdefault("pageSize", self.MAX_PAGE_SIZE)
            response = self.client.get(
                endpoint,
                page=page_number,
                **params,
            )
            page_number = response["page"] + 1
            yield from response["records"]

    def list_imported_files(self, root_item):
        """
        Iterate over each imported file for every library item.

        :param root_item: The dictionary from the Servarr API JSON for the top-level
            library item, for example series or movie.
        :return: Iterator of Servarr JSON API imported item dictionaries.
        """
        # Map item file IDs for correlating to the items:
        item_files = {
            item_file["id"]: item_file
            for item_file in self.client.get(
                f"{self.type_map['item_type']}File",
                **{f"{self.type_map['dir_type']}Id": root_item["id"]},
            )
        }
        # Is there a 2nd level to get to files, for example series -> episode ->
        # file as opposed to just movie -> file:
        items = (
            [root_item]
            if self.type_map["file_depth"] == 1
            else self.client.get(
                self.type_map["item_type"],
                **{f"{self.type_map['dir_type']}Id": root_item["id"]},
            )
        )
        # Then iterate over the imported files:
        for imported_item in items:
            if not imported_item["hasFile"] is True:
                continue
            imported_item["file"] = item_files[
                imported_item[f"{self.type_map['item_type']}FileId"]
            ]
            imported_item["file"]["path"] = pathlib.Path(
                imported_item["file"]["path"],
            )
            imported_item["file"]["relative"] = imported_item["file"][
                "path"
            ].relative_to(
                imported_item["file"]["path"].parents[self.type_map["file_depth"] - 1]
            )
            yield imported_item

    def collect_data_paths(self, extra_data_paths=None):
        """
        Collect the paths to search for download item data from the download clients.

        :param extra_data_paths: Additional download client paths whose immediate
            children might contain download item data.
        :return: The full list of data paths including those from the Servarr download
            clients.
        """
        if extra_data_paths is None:
            extra_data_paths = []
        # Add the paths in the download clients that this servarr instance deals
        # with:
        data_paths = []
        for servarr_download_client in self.download_clients.values():
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
        return list(dict.fromkeys(data_paths))

    def collate_export_history(self, data_paths, root_item):
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

        :param data_paths: The full list of data paths including those from the Servarr
            download clients.
        :param root_item: The dictionary from the Servarr API JSON for the top-level
            library item, for example series or movie.
        :return: A dictionary mapping the history records by various means.
        """
        mapped_history = {
            "importedRel": {},
            "downloadId": {},
            "sourceTitle": {},
            "downloadRootName": {},
        }
        for history_record in self.client.get(
            f"history/{self.type_map['dir_type']}",
            **{f"{self.type_map['dir_type']}Id": root_item["id"]},
        ):
            if history_record["eventType"] not in {
                "grabbed",
                "downloadFolderImported",
            }:  # pragma: no cover
                continue

            # Derive the relative path to the imported file if present in this history
            # record:
            imported_path = imported_relative = None
            if history_record["data"].get("importedPath"):
                imported_path = pathlib.Path(history_record["data"]["importedPath"])
                imported_relative = imported_path.relative_to(
                    imported_path.parents[self.type_map["file_depth"] - 1],
                )

            # Determine which part of the paths are from the download item:
            dropped_relative = None
            if history_record["data"].get("droppedPath"):
                dropped_path = pathlib.Path(history_record["data"]["droppedPath"])
                for data_path in data_paths:
                    if data_path.resolve() in dropped_path.resolve().parents:
                        dropped_relative = dropped_path.resolve().relative_to(data_path)
                        mapped_history["importedRel"].setdefault(
                            imported_relative,
                            {},
                        ).setdefault("droppedRel", dropped_relative)
                        mapped_history["importedRel"].setdefault(
                            imported_relative,
                            {},
                        ).setdefault(
                            "location",
                            dropped_path.parents[len(dropped_relative.parts) - 1],
                        )
                        break
                else:
                    logger.error(
                        "No download root name found: %s",
                        dropped_path,
                    )

            # The most common case, map an imported path to a download item ID/hash:
            if history_record["data"].get("importedPath") and history_record.get(
                "downloadId"
            ):
                # Match on relative paths to tolerate items imported before Servarr
                # renamed the top-level series/movie:
                mapped_history["importedRel"].setdefault(
                    imported_relative,
                    {},
                ).setdefault(
                    "downloadId",
                    history_record["downloadId"],
                )

            # Map download item IDs/hashes to download URLs if download items need to be
            # re-added to the download client:
            if history_record["data"].get("downloadUrl") and history_record.get(
                "downloadId"
            ):
                # Match this grab history to it's download client:
                if (
                    history_record["data"]["downloadClientName"]
                    in self.download_client_names
                ):
                    download_client = self.download_client_names[
                        history_record["data"]["downloadClientName"]
                    ]
                else:  # pragma: no cover
                    logger.warning(
                        "Download client name not found, defaulting to first: %s",
                        history_record["data"]["downloadClientName"],
                    )
                    download_client = list(
                        self.download_client_names.values(),
                    )[0]
                mapped_history["downloadId"].setdefault(
                    history_record["downloadId"],
                    {},
                ).setdefault(history_record["data"]["downloadUrl"], download_client)

            # If the import history has no download item ID/hash, then try to guess the
            # download item by other means:
            collate_export_history_guesses(
                mapped_history,
                imported_relative,
                dropped_relative,
                history_record,
            )

        return mapped_history


def collate_export_history_guesses(
    mapped_history,
    imported_relative,
    dropped_relative,
    history_record,
):
    """
    Try to guess the download item for an imported file by means other than ID/hash.

    :param mapped_history: A dictionary mapping the history records by various
        means.
    :param imported_relative: The relative path to the imported file within the
        series/movie.
    :param dropped_relative: The relative path to the download item file within the
        download item ``downloadDir``.
    :param history_record: The dictionary from the Servarr API JSON for the
        individual history record.
    """
    # If the import history has no download item ID/hash, try to match on the
    # download item name in `sourceTitle`:
    if history_record.get("sourceTitle"):  # pragma: no cover
        if history_record.get("downloadId"):
            mapped_history["sourceTitle"].setdefault(
                history_record["sourceTitle"],
                history_record["downloadId"],
            )
        if history_record["data"].get("importedPath"):
            # Match on relative paths to tolerate items imported before Servarr
            # renamed the top-level series/movie:
            mapped_history["importedRel"].setdefault(
                imported_relative,
                {},
            ).setdefault(
                "sourceTitle",
                history_record["sourceTitle"],
            )

    # As a last resort, derive the download item's root basename from the import
    # history and match that to a download item ID/hash:
    if history_record["data"].get("droppedPath"):
        if dropped_relative:
            if history_record.get("downloadId"):
                mapped_history["downloadRootName"].setdefault(
                    dropped_relative.parts[0],
                    history_record["downloadId"],
                )
            if history_record["data"].get("importedPath"):  # pragma: no cover
                mapped_history["importedRel"].setdefault(
                    # Match on relative paths to tolerate items imported
                    # before Servarr renamed the top-level series/movie:
                    imported_relative,
                    {},
                ).setdefault(
                    "downloadRootName",
                    dropped_relative.parts[0],
                )


def lookup_download_ids(
    download_ids_by_name,
    mapped_history,
    imported_items,
    import_keys=("sourceTitle", "downloadRootName"),
):
    """
    Lookup the download IDs for imported files without them by download item name.

    :param download_ids_by_name: Map download item root basenames to the items.
    :param mapped_history: A dictionary mapping the history records by various
        means.
    :param imported_items: The dictionaries from the Servarr API JSON for the
        individual imported files.
    :param import_keys: What top-level keys in the ``imported_items`` whose values to
        match against download item names. The order defines precedence.
    """
    download_ids = {}
    for imported_item in imported_items:
        download_id = (
            mapped_history["importedRel"]
            .get(
                imported_item["file"]["relative"],
                {},
            )
            .get("downloadId")
        )
        if download_id:
            continue

        imported_data = mapped_history["importedRel"].get(
            imported_item["file"]["relative"],
            {},
        )
        for import_key in import_keys:
            if not (import_name := imported_data.get(import_key)):  # pragma: no cover
                continue

            for mapped_names in (mapped_history, download_ids_by_name):
                if download_id := download_ids.get(import_key, {}).get(
                    import_name
                ):  # pragma: no cover
                    logger.debug(
                        "Reusing previous download item %r name lookup, %r: %s",
                        import_key,
                        import_name,
                        imported_item["file"]["path"],
                    )
                elif download_id := mapped_names[import_key].get(import_name):
                    logger.info(
                        "Matched download item by %r name, %r: %s",
                        import_key,
                        import_name,
                        imported_item["file"]["path"],
                    )
                    download_ids.setdefault(import_key, {}).setdefault(
                        import_name,
                        download_id,
                    )

                if download_id:
                    mapped_history["importedRel"][
                        imported_item["file"]["relative"]
                    ].setdefault("downloadId", download_id)
                    break

            if download_id:
                break

        else:
            logger.error(
                "Could not lookup download item by names: %s",
                imported_item["file"]["path"],
            )

    return download_ids


def maybe_add_download_item(
    download_items_by_id,
    download_ids_by_name,
    download_id,
    download_urls,
):
    """
    Add a download item from the given URL if not already in the download client.

    :param download_items_by_id: Map download item hashes to the items.
    :param download_ids_by_name: Map download item root basenames to the items.
    :param download_id: The download item ID/hash.
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
    for download_url, download_client in download_urls.items():
        try:
            download_item = download_client.download_client.add_torrent(
                download_url,
                paused=True,
                download_dir=str(download_client.seeding_dir),
            )
        except requests.exceptions.RequestException:  # pragma: no cover
            logger.exception(
                "Exception downloading torrent: %s",
                download_url,
            )
            continue
        except transmission_rpc.error.TransmissionError:  # pragma: no cover
            # Tolerate exceptions adding torrents because the download
            # URL may no longer be valid, IOW 404:
            logger.exception(
                "Exception adding torrent: %s",
                download_url,
            )
            continue
        else:
            download_items_by_id.setdefault(
                download_item.hashString.upper(),
                [],
            ).append(download_item)
            download_ids_by_name["sourceTitle"].setdefault(
                download_item.name,
                download_item.hashString.upper(),
            )
            download_ids_by_name["downloadRootName"].setdefault(
                download_item.root_name,
                download_item.hashString.upper(),
            )
            return download_item

    return None  # pragma: no cover


class PrunerrServarrDownloadClient:
    """
    A specific Servar instance's individual specific download client.
    """

    download_client = None
    download_dir = None
    seeding_dir = None

    def __init__(self, servarr):
        """
        Capture a references to the servarr instance and download client.
        """
        self.servarr = servarr
        self.config = {}

    def __repr__(self):
        """
        Readable, informative, and specific representation to ease debugging.
        """
        return (
            f"<{type(self).__name__} {self.servarr.config.get('name')!r}"
            f"->{self.config.get('url')!r}>"
        )

    def update(self, config):
        """
        Update download client configuration specific to this Servarr instance.
        """
        self.config = config
        # Assemble the download client paths managed by Servarr
        self.download_dir = pathlib.Path(
            self.config["fieldValues"][self.servarr.type_map["download_dir_field"]]
        ).resolve()
        return self.download_dir

    def move(self, move_timeout=5 * 60):
        """
        Move download items that have been acted on by Servarr into the seeding dir.

        Move all download items that are seeding, that are in this Servarr instance's
        download directory, and aren't in this Servarr instance's queue.  Also only
        include items that have some Servarr history events other than `grabbed` to
        prevent moving manually grabbed items out from under Servarr before it's had a
        chance to recognize notice them.
        """
        download_items = [
            download_item
            for download_item in self.download_client.items
            # Skip items still downloading
            if download_item.status == "seeding"
            # Skip items known by a Servarr instance in it's queue
            and download_item.hashString.upper() not in self.servarr.queue
            # Skip items not in this Servarr instance's download directory for this
            # download client
            and self.download_dir in download_item.path.parents
            # Skip items with no history other than `grabbed` events
            and [
                history_record
                for history_record in self.servarr.get_api_paged_records(
                    "history",
                    downloadId=download_item.hashString.upper(),
                )
                if history_record["eventType"] != "grabbed"
            ]
        ]
        if not download_items:
            logger.debug(
                "No %s download items to move",
                self.servarr.config["name"],
            )
            return None
        logger.info(
            "Moving download items: %r -> %r\n  %s",
            str(self.download_dir),
            str(self.seeding_dir),
            "\n  ".join(repr(download_item) for download_item in download_items),
        )
        self.download_client.client.move_torrent_data(
            ids=[download_item.hashString for download_item in download_items],
            location=self.seeding_dir,
        )
        # Wait for a timeout for items to finish moving before proceeding.
        start = time.time()
        while next(  # pylint: disable=while-used
            (
                download_item
                for download_item in download_items
                if download_item.path.exists()
            ),
            None,
        ):
            if time.time() - start > move_timeout:
                raise prunerr.downloadclient.DownloadClientTimeout(
                    f"Timed out waiting for {self.servarr.config['name']} items "
                    "to finish moving",
                )
            time.sleep(1)
        # Update the download item's dir for subsequent operations, done manually to
        # minimize requests.
        for download_item in download_items:
            download_item._fields[download_item.DOWNLOAD_DIR_FIELD] = (
                download_item._fields[download_item.DOWNLOAD_DIR_FIELD]._replace(
                    value=self.seeding_dir
                )
            )
            vars(download_item).pop("path", None)
        return [download_item.hashString for download_item in download_items]


def deserialize_servarr_download_client(download_client_config):
    """
    Assemble field values and a URL for a Servarr download client configuration.
    """
    download_client_config["fieldValues"] = {
        download_client_config_field["name"]: download_client_config_field["value"]
        for download_client_config_field in download_client_config["fields"]
        if "value" in download_client_config_field
    }
    netloc = f"{download_client_config['fieldValues']['host']}"
    if download_client_config["fieldValues"].get("port") is not None:
        netloc = f"{netloc}:{download_client_config['fieldValues']['port']}"
    if download_client_config["fieldValues"].get("username"):
        netloc = f"{download_client_config['fieldValues']['username']}@{netloc}"
    download_client_config["url"] = urllib.parse.SplitResult(
        "http" if not download_client_config["fieldValues"]["useSsl"] else "https",
        netloc,
        download_client_config["fieldValues"]["urlBase"],
        "",
        "",
    ).geturl()
    return download_client_config
