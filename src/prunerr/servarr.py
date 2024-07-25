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
import logging
import typing

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
            "file_has_multi": True,
            "client": arrapi.SonarrAPI,
            "download_dir_field": "tvDirectory",
            "rename_template": (
                "{series[title]} - {episode[seasonEpisode]} - {episode[title]}"
            ),
            "file_depth": 2,
        },
        "radarr": {
            "dir_type": "movie",
            "item_type": "movie",
            "file_has_multi": False,
            "client": arrapi.RadarrAPI,
            "download_dir_field": "movieDirectory",
            "rename_template": "{movie[title]} ({movie[release_year]})",
            "file_depth": 1,
        },
    }
    MAX_PAGE_SIZE = 250

    client = None
    queue = None

    def __init__(self, runner):
        """
        Capture a references to the runner and individual Servarr configuration.
        """
        self.runner = runner
        self.config = {}
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

        logger.debug(
            "Connecting to %s",
            self.config["name"],
        )
        self.client = PrunerrServarrAPIClient(
            self.TYPE_MAPS[self.config["type"]]["client"](
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
        :return: Map download client items to any files have been linked.
        """
        # Map download item IDs to its imported files:
        imports_by_download = self.map_downloads_to_files(extra_data_paths)

        # Ensure that the download client has a download item for each download ID:
        download_items_by_id: dict = {}
        for download_client_name, download_ids in imports_by_download.items():
            if download_client_name is None:
                # Manual import record with no grab record and this now download URL:
                continue
            self.download_client_names[download_client_name].maybe_add_download_items(
                download_client_name,
                download_items_by_id,
                download_ids,
            )

        # Lookup the download IDs for imported files without them by download item name:
        imports_by_download = self.lookup_download_ids(imports_by_download)

        # Locate existing download item data in known directories and set the best
        # candidate as the download item's location:
        export_results: dict = self.link_imported_files(
            imports_by_download,
            download_items_by_id,
            extra_data_paths,
        )

        # Report results if any:
        if export_results:
            return export_results
        return None

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

    def list_imported_files(self):
        """
        Iterate over each imported file for every library item.

        :return: Iterator of Servarr JSON API imported item dictionaries.
        """
        # Iterate over all top-level items in the library:
        type_map = self.TYPE_MAPS[self.config["type"]]
        for root_item in self.client.get(type_map["dir_type"]):
            # Map item file IDs for correlating to the items:
            item_files = {
                item_file["id"]: item_file
                for item_file in self.client.get(
                    f"{type_map['item_type']}File",
                    **{f"{type_map['dir_type']}Id": root_item["id"]},
                )
            }
            # Is there a 2nd level to get to files, for example series -> episode ->
            # file as opposed to just movie -> file:
            items = (
                [root_item]
                if type_map["file_depth"] == 1
                else self.client.get(
                    type_map["item_type"],
                    **{f"{type_map['dir_type']}Id": root_item["id"]},
                )
            )
            # Then iterate over the imported files:
            for imported_item in items:
                if not imported_item["hasFile"] is True:
                    continue
                imported_item["file"] = item_files[
                    imported_item[f"{type_map['item_type']}FileId"]
                ]
                imported_item["file"]["path"] = pathlib.Path(
                    imported_item["file"]["path"],
                )
                imported_item["file"]["relative"] = imported_item["file"][
                    "path"
                ].relative_to(
                    imported_item["file"]["path"].parents[type_map["file_depth"] - 1]
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

    def map_downloads_to_files(self, extra_data_paths=None):
        """
        Collate the Servarr history for all imported files by download item ID.

        Imported files without grab history records, such as manual imports, cannot be
        mapped to download IDs. The download item name for those files is determined by
        searching the immediate children of the data paths known to Servarr and those
        paths in ``extra_data_paths`` for those that match the beginning of the
        ``droppedPath``. Another dictionary mapping those download item names to
        imported files is returned under the ``None`` key.

        :param extra_data_paths: Additional download client paths whose immediate
            children might contain download item data.
        :return: Map download client names to download item IDs to that item's Servarr
            JSON API import item dictionaries.
        """
        data_paths = self.collect_data_paths(extra_data_paths)

        imports_by_download = {}
        for imported_item in self.list_imported_files():
            imported_item["history"] = self.collate_item_history(imported_item)

            if (
                import_record := imported_item["history"]["downloadFolderImported"]
            ) is None:
                continue

            # Determine which part of the paths are from the download item:
            for data_path in data_paths:
                if (
                    data_path.resolve()
                    in import_record["data"]["droppedPath"].resolve().parents
                ):
                    import_record["data"]["droppedRel"] = (
                        import_record["data"]["droppedPath"]
                        .resolve()
                        .relative_to(data_path)
                    )
                    import_record["data"]["location"] = import_record["data"][
                        "droppedPath"
                    ].parents[len(import_record["data"]["droppedRel"].parts) - 1]
                    import_record["data"]["downloadName"] = import_record["data"][
                        "droppedRel"
                    ].parts[0]
                    break
            else:
                logger.error(
                    "No download root name found: %s",
                    imported_item["file"]["path"],
                )

            if download_id := import_record.get("downloadId"):
                if (grab_record := imported_item["history"]["grabbed"]) is not None:
                    # Map download client names download item IDs to its imported files:
                    imports_by_download.setdefault(
                        grab_record["data"]["downloadClientName"],
                        {},
                    ).setdefault(download_id, {}).setdefault(
                        grab_record["data"]["downloadUrl"],
                        [],
                    ).append(
                        imported_item,
                    )
                else:  # pragma: no cover
                    # I found at least two real-world examples of this. I'm guessing
                    # this happens when importing a download item that was added to the
                    # download client outside of Servarr. I think this can also happen
                    # when a multi-season pack requires manual intervention and ends up
                    # importing more files than it was grabbed for:
                    logger.debug(
                        "No grab history for import history with download hash: %s",
                        imported_item["file"]["path"],
                    )
            elif "downloadName" in import_record["data"]:  # pragma: no cover
                logger.warning(
                    "No download hash found, checking download root name: %s",
                    imported_item["file"]["path"],
                )
                # Find download item root name from data_paths:
                imports_by_download.setdefault(None, {}).setdefault(
                    import_record["data"].get("downloadName"),
                    [],
                ).append(imported_item)

        return imports_by_download

    def collate_item_history(self, imported_item):
        """
        Collate the Servarr history for one imported file.

        :param imported_item: The dictionary from the Servarr API JSON for the imported
            file.
        :return: A dictionary mapping event types to their most recent records for the
            imported file.
        """
        import_record = grab_record = None
        params = {
            "pageSize": 1000,
            "sortKey": "date",
            "sortDirection": "descending",
        }
        type_map = self.TYPE_MAPS[self.config["type"]]
        params[f"{type_map['item_type']}Id"] = imported_item["id"]
        for history_record in self.get_api_paged_records("history", **params):
            # Assume the most recent import record corresponds to the current file:
            if (
                history_record["eventType"] == "downloadFolderImported"
                and import_record is None
            ):
                history_record["data"]["importedPath"] = pathlib.Path(
                    history_record["data"]["importedPath"],
                )
                history_record["data"]["importedRel"] = history_record["data"][
                    "importedPath"
                ].relative_to(
                    history_record["data"]["importedPath"].parents[
                        type_map["file_depth"] - 1
                    ]
                )
                history_record["data"]["droppedPath"] = pathlib.Path(
                    history_record["data"]["droppedPath"],
                )
                # Match on relative paths to tolerate items imported before Servarr
                # renamed the top-level series/movie:
                if (
                    history_record["data"]["importedRel"]
                    == imported_item["file"]["relative"]
                ):
                    import_record = history_record
                    if download_id := import_record.get("downloadId"):
                        # Can match to a subsequent download record:
                        continue
                    if download_id is not None:  # pragma: no cover
                        raise ValueError(
                            "Import record contains and empty download hash: "
                            f"{imported_item['path']}",
                        )
                    # Probably a manual import, no need to keep looking:
                    break
                logger.error(
                    "Import record for different file found before for current "
                    "file: %r != %r",
                    str(history_record["data"]["importedPath"]),
                    str(imported_item["file"]["path"]),
                )
            # Find the most recent grab record that corresponds to the import
            # record:
            if (
                import_record is not None
                and history_record["eventType"] == "grabbed"
                and history_record["downloadId"] == import_record["downloadId"]
            ):
                grab_record = history_record
                if (
                    grab_record["data"]["downloadClientName"]
                    in self.download_client_names
                ):
                    grab_record["data"]["downloadClient"] = self.download_client_names[
                        grab_record["data"]["downloadClientName"]
                    ].download_client
                else:  # pragma: no cover
                    logger.warning(
                        "Download client name not found, defaulting to first: %s",
                        grab_record["data"]["downloadClientName"],
                    )
                    grab_record["data"]["downloadClient"] = list(
                        self.download_client_names.values(),
                    )[0]
                    grab_record["data"]["downloadClientName"] = list(
                        self.download_client_names.keys(),
                    )[0]
                break
            # Don't proceed past previous imports:
            if (
                history_record["eventType"] == "downloadFolderImported"
                and import_record is not None
            ):  # pragma: no cover
                logger.debug(
                    "Skipping previous import history: %s",
                    history_record["data"]["importedPath"],
                )
                break
        else:
            if import_record is None:  # pragma: no cover
                # At lease one use case leads to this, existing files added to the
                # library outside of Servarr. IOW, when files are put in place and then
                # scanned by Servarr without ever having grabbed or imported them. This
                # will be true for all existing files in place before "installing"
                # Servarr:
                logger.warning(
                    "No import record found for file: %s",
                    imported_item["file"]["path"],
                )

        return {"downloadFolderImported": import_record, "grabbed": grab_record}

    def lookup_download_ids(self, imports_by_download):
        """
        Lookup the download IDs for imported files without them by download item name.

        :param imports_by_download: Map download client names to download item IDs to
        :return: Map download client names to download item IDs to that item's Servarr
            JSON API import item dictionaries.
        """
        items_by_name = {}
        for servarr_download_client in self.download_clients.values():
            for download_item in servarr_download_client.download_client.items:
                items_by_name.setdefault(download_item.root_name, []).append(
                    download_item,
                )
        for download_name, import_items in list(
            imports_by_download.get(None, {}).items(),
        ):
            if not (download_items := items_by_name.get(download_name)):
                logger.error(
                    "No download item found for root name: %s",
                    download_name,
                )
                continue
            if len(download_items) > 1:
                logger.error(
                    "Multiple download items named: %s",
                    download_name,
                )
            for import_item in import_items:
                import_item["history"]["downloadFolderImported"][
                    "downloadId"
                ] = download_items[0].hashString.upper()
                for download_ids in imports_by_download.values():
                    logger.warning(
                        "Matched download root name to download item: %r -> %r",
                        download_name,
                        download_items[0],
                    )
                    download_ids.setdefault(
                        download_items[0].hashString.upper(),
                        {},
                    ).setdefault(None, []).append(import_item)
        imports_by_download.pop(None, None)

        return imports_by_download

    def link_imported_files(
        self,
        imports_by_download,
        download_items_by_id,
        extra_data_paths=None,
    ):
        """
        Hard link imported files back into download items.

        :param imports_by_download: Map download client names to download item IDs to
        that item's Servarr JSON API import item dictionaries.
        :param extra_data_paths: Additional download client paths whose immediate
            children might contain download item data.
        :return: Map download client items to any files have been linked.
        """
        data_paths = self.collect_data_paths(extra_data_paths)

        export_results = {}
        for download_client_name, download_ids in imports_by_download.items():
            for download_id, download_urls in download_ids.items():
                if (
                    download_id not in download_items_by_id[download_client_name]
                ):  # pragma: no cover
                    logger.debug(
                        "No download item in client for hash %r: %s",
                        download_id,
                        list(download_urls.keys())[0],
                    )
                    continue

                download_item = download_items_by_id[download_client_name][download_id]
                need_verify = False

                # Change the download item data path if a better one is found:
                # Collect additional possible data paths from the import history
                # records:
                if download_item.find_location(
                    collect_item_data_paths(data_paths, download_urls),
                ):
                    need_verify = True

                # Hard link imported files into the download item's location:
                for import_items in download_urls.values():
                    for import_item in import_items:
                        if "droppedRel" in import_item["history"][
                            "downloadFolderImported"
                        ]["data"] and maybe_link_file(
                            download_item.download_dir
                            / import_item["history"]["downloadFolderImported"]["data"][
                                "droppedRel"
                            ],
                            import_item["file"]["path"],
                        ):
                            need_verify = True
                            export_results.setdefault(
                                download_client_name,
                                {},
                            ).setdefault(download_id, []).append(
                                str(import_item["file"]["path"]),
                            )

                if need_verify:
                    # Deselect for download any remaining incomplete files:
                    download_item.deselect_unimported_files()

                    logger.info(
                        "Verifying and resuming download item: %r",
                        download_item,
                    )
                    download_item.download_client.client.verify_torrent(
                        download_item.hashString,
                    )
                    download_item.start()

            return export_results


def collect_item_data_paths(data_paths, download_urls):
    """
    Include per-item data paths from Servarr import history.

    :param data_paths: The global set of download client paths whose immediate
        children might contain download item data.
    :return: The full list of data paths including those from the this item's import
        history.
    """
    item_data_paths = dict.fromkeys(data_paths)
    for import_items in download_urls.values():
        for import_item in import_items:
            if "location" in import_item["history"]["downloadFolderImported"]["data"]:
                item_data_paths[
                    import_item["history"]["downloadFolderImported"]["data"]["location"]
                ] = None
    return list(item_data_paths)


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
            self.config["fieldValues"][
                self.servarr.TYPE_MAPS[self.servarr.config["type"]][
                    "download_dir_field"
                ]
            ]
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

    def maybe_add_download_items(
        self,
        download_client_name,
        download_items_by_id,
        download_ids,
    ):
        """
        Add a download item from the given URL if not already in the download client.

        :param download_client_name: The name of the download client in Servarr.
        :param download_items_by_id: Map download item hashes to the items.
        :param download_ids: Map download item hashes to download item URLs.
        """
        download_items_by_id[download_client_name] = {
            item.hashString.upper(): item for item in self.download_client.items
        }
        for download_id, download_urls in download_ids.items():
            if download_id in download_items_by_id[download_client_name]:
                logger.debug(
                    "Skipping already added torrent: %s",
                    list(download_urls.keys())[0],
                )
                continue
            if len(download_urls) > 1:  # pragma: no cover
                logger.warning(
                    "Multiple grab URLs for the same download item: %s",
                    download_id,
                )
            for download_url in download_urls.keys():
                if (
                    urllib.parse.urlsplit(download_url).scheme == "magnet"
                ):  # pragma: no cover
                    # Supporting adding magnet torrents would be a PITA because we'd
                    # have to use a torrent cache to get torrent files which feels
                    # like too much trouble for mostly public torrents:
                    logger.error(
                        "Skipping magnet torrent: %s",
                        download_url,
                    )
                else:
                    try:
                        download_items_by_id[download_client_name][
                            download_id
                        ] = self.download_client.add_torrent(
                            download_url,
                            paused=True,
                            download_dir=str(self.seeding_dir),
                        )
                    except transmission_rpc.error.TransmissionError:  # pragma: no cover
                        # Tolerate exceptions adding torrents because the download
                        # URL may no longer be valid, IOW 404:
                        logger.exception(
                            "Exception adding torrent: %s",
                            download_url,
                        )
                    else:
                        break


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
