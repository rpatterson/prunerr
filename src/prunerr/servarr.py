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

    type_map = None
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
        :return: Map download client items to any files have been linked.
        """
        data_paths = self.collect_data_paths(extra_data_paths)

        # Map download item IDs to its imported files:
        download_items_by_id, imports_by_download = self.map_downloads_to_files(
            data_paths,
        )

        # Locate existing download item data in known directories and set the best
        # candidate as the download item's location:
        export_results: dict = link_imported_files(
            data_paths,
            download_items_by_id,
            imports_by_download,
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

    def map_downloads_to_files(self, data_paths):
        """
        Collate the Servarr history for all imported files by download item ID.

        Imported files without grab history records, such as manual imports, cannot be
        mapped to download IDs. The download item name for those files is determined by
        searching the immediate children of the data paths known to Servarr and those
        paths in ``extra_data_paths`` for those that match the beginning of the
        ``droppedPath``. Another dictionary mapping those download item names to
        imported files is returned under the ``None`` key.

        :param data_paths: The full list of data paths including those from the Servarr
            download clients.
        :return: Map download item IDs to that item's Servarr JSON API import item
            dictionaries.
        """
        # First collect all the download hashes we need to have in the download client:
        imports_by_download = {}
        grab_history = {}
        for root_item in self.client.get(self.type_map["dir_type"]):
            for imported_item in self.list_imported_files(root_item):
                import_record = self.find_import_history(data_paths, imported_item)
                if import_record is None:
                    # Logged in `self.find_import_history()`
                    continue
                imported_item["history"] = {"downloadFolderImported": import_record}
                imports_by_download.setdefault(
                    import_record.get("downloadId"),
                    [],
                ).append(imported_item)
            grab_history.update(self.collate_grab_history(root_item))

        # Next, ensure all download hashes are in the download client, re-adding the
        # items if necessary:
        download_items_by_id = {}
        for client in self.download_client_names.values():
            download_items_by_id.update(
                (item.hashString.upper(), item) for item in client.download_client.items
            )
        for download_id, imported_items in imports_by_download.items():
            if download_id in grab_history:
                grab_record = grab_history[download_id]
                if (
                    grab_record["data"]["downloadClientName"]
                    in self.download_client_names
                ):
                    grab_record["data"]["downloadClient"] = self.download_client_names[
                        grab_record["data"]["downloadClientName"]
                    ]
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
                grab_record["data"]["downloadClient"].maybe_add_download_item(
                    download_items_by_id,
                    grab_record,
                )
                for imported_item in imported_items:
                    imported_item["history"]["grabbed"] = grab_record
            else:
                # The import history *does* have a download hash but there's *no*
                # corresponding grab history. I found at least two real-world
                # examples of this. I'm guessing this happens when importing a
                # download item that was added to the download client outside of
                # Servarr. I think this can also happen when a multi-season pack
                # requires manual intervention and ends up importing more files than
                # it was grabbed for:
                logger.debug(
                    "No grab history for import history with download hash: %s",
                    imported_items[0]["file"]["path"],
                )

        # Now that all download items are populated in the download client, we can
        # map download item root names to the download items and then map imported
        # items without download item hashes to download items using the root name:
        imports_by_download = self.lookup_download_ids(
            imports_by_download,
            grab_history,
        )

        return download_items_by_id, imports_by_download

    def lookup_download_ids(self, imports_by_download, grab_history):
        """
        Lookup the download IDs for imported files without them by download item name.

        :param imports_by_download: Map download client names to download item IDs to
        :param grab_history: Map download item hashes to the download item's most recent
            grab history record.
        :return: Map download client names to download item IDs to that item's Servarr
            JSON API import item dictionaries.
        """
        download_items_by_name = {}
        for client in self.download_client_names.values():
            for item in client.download_client.items:
                download_items_by_name.setdefault(item.root_name, item)
        for imported_item in imports_by_download.get(None, []):
            download_name = imported_item["history"]["downloadFolderImported"][
                "data"
            ].get("downloadName")
            if download_name is None:  # pragma: no cover
                continue
            if download_name in download_items_by_name:
                logger.warning(
                    "Lookup download hash by download root name %r: %s",
                    download_name,
                    imported_item["file"]["path"],
                )
                download_id = download_items_by_name[download_name].hashString.upper()
                imports_by_download.setdefault(download_id, []).append(
                    imported_item,
                )
                imported_item["history"]["grabbed"] = grab_history.get(download_id)
            else:
                logger.error(
                    "No download item found by root name: %s",
                    imported_item["file"]["path"],
                )

        imports_by_download.pop(None, None)
        return imports_by_download

    def collate_grab_history(self, root_item):
        """
        Map grab history records by download ID and download root name.

        :param root_item: The dictionary from the Servarr API JSON for the top-level
            library item, for example series or movie.
        :return: A dictionary mapping the download history records with the ``None`` key
            containing a dictionary mapping download root names to records.
        """
        grab_history = {}
        for history_record in self.client.get(
            f"history/{self.type_map['dir_type']}",
            **{f"{self.type_map['dir_type']}Id": root_item["id"]},
        ):
            if history_record["eventType"] != "grabbed":
                continue
            grab_history.setdefault(history_record["downloadId"], history_record)

        return grab_history

    def find_import_history(self, data_paths, imported_item):
        """
        Locate the latest Servarr history for this imported file.

        :param data_paths: The global set of download client paths whose immediate
            children might contain download item data.
        :param imported_item: The dictionary from the Servarr API JSON for the imported
            item, for example episode or movie.
        :return: The dictionary from the Servarr API JSON for the import history record.
        """
        import_record = None
        endpoint = (
            "history"
            if not self.type_map["item_history_is_typed"]
            else f"history/{self.type_map['item_type']}"
        )
        params = {f"{self.type_map['item_type']}Id": imported_item["id"]}
        for history_record in (
            self.get_api_paged_records(
                endpoint,
                **dict(
                    params,
                    **{
                        "pageSize": 1000,
                        "sortKey": "date",
                        "sortDirection": "descending",
                    },
                ),
            )
            if self.type_map["item_history_is_paged"]
            else self.client.get(endpoint, **params)
        ):
            if (
                history_record["eventType"] != "downloadFolderImported"
            ):  # pragma: no cover
                continue

            # Match on relative paths to tolerate items imported before Servarr renamed
            # the top-level series/movie:
            history_record["data"]["importedPath"] = pathlib.Path(
                history_record["data"]["importedPath"],
            )
            history_record["data"]["importedRel"] = history_record["data"][
                "importedPath"
            ].relative_to(
                history_record["data"]["importedPath"].parents[
                    self.type_map["file_depth"] - 1
                ]
            )
            if (
                history_record["data"]["importedRel"]
                == imported_item["file"]["relative"]
            ):
                import_record = history_record
                # Don't proceed past the most recent import record:
                break
            logger.error(
                "Import record for different file found before for current "
                "file: %r != %r",
                str(history_record["data"]["importedPath"]),
                str(imported_item["file"]["path"]),
            )
            return None
        else:  # pragma: no cover
            # At lease one use case leads to this, existing files added to the
            # library outside of Servarr. IOW, when files are put in place and then
            # scanned by Servarr without ever having grabbed or imported them. This
            # will be true for all existing files in place before "installing"
            # Servarr:
            logger.warning(
                "No import history found for file: %s",
                imported_item["file"]["path"],
            )
            return None

        # Determine which part of the paths are from the download item:
        import_record["data"]["droppedPath"] = pathlib.Path(
            import_record["data"]["droppedPath"],
        )
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

        return import_record


def link_imported_files(
    data_paths,
    download_items_by_id,
    imports_by_download,
):
    """
    Hard link imported files back into download items.

    :param data_paths: The full list of data paths including those from the Servarr
        download clients.
    :param download_items_by_id: Map download client names to download item
        hashes/IDs to that the download item.
    :param imports_by_download: Map download item IDs to that item's Servarr JSON
        API import item dictionaries.
    :return: Map download client items to any files have been linked.
    """
    export_results = {}
    for download_id, imported_items in imports_by_download.items():
        if download_id not in download_items_by_id:  # pragma: no cover
            # Logged in `PrunerrServarrDownloadClient.maybe_add_download_item()`:
            continue

        download_item = download_items_by_id[download_id]
        need_verify = False

        # Change the download item data path if a better one is found:
        # Collect additional possible data paths from the import history
        # records:
        if download_item.find_location(
            collect_item_data_paths(data_paths, imported_items),
        ):
            need_verify = True

        # Hard link imported files into the download item's location:
        for import_item in imported_items:
            if "droppedRel" in import_item["history"]["downloadFolderImported"][
                "data"
            ] and maybe_link_file(
                download_item.download_dir
                / import_item["history"]["downloadFolderImported"]["data"][
                    "droppedRel"
                ],
                import_item["file"]["path"],
            ):
                need_verify = True
                export_results.setdefault(download_id, []).append(
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


def collect_item_data_paths(data_paths, imported_items):
    """
    Include per-item data paths from Servarr import history.

    :param data_paths: The global set of download client paths whose immediate
        children might contain download item data.
    :param imported_items: Servarr JSON API import item dictionaries.
    :return: The full list of data paths including those from the this item's import
        history.
    """
    item_data_paths = dict.fromkeys(data_paths)
    for import_item in imported_items:
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
            download_item._fields["downloadDir"] = download_item._fields[
                "downloadDir"
            ]._replace(value=self.seeding_dir)
            vars(download_item).pop("path", None)
        return [download_item.hashString for download_item in download_items]

    def maybe_add_download_item(
        self,
        download_items_by_id,
        grab_record,
    ):
        """
        Add a download item from the given URL if not already in the download client.

        :param download_items_by_id: Map download item hashes to the items.
        :param grab_record: The Servarr API JSON dictionary representing the grab
            history record.
        :return: The added download item if one was added.
        """
        if grab_record["downloadId"] in download_items_by_id:
            logger.debug(
                "Skipping already added torrent: %s",
                grab_record["sourceTitle"],
            )
            return None
        if (
            urllib.parse.urlsplit(
                grab_record["data"]["downloadUrl"],
            ).scheme
            == "magnet"
        ):  # pragma: no cover
            # Supporting adding magnet torrents would be a PITA because we'd
            # have to use a torrent cache to get torrent files which feels
            # like too much trouble for mostly public torrents:
            logger.error(
                "Skipping magnet torrent: %s",
                grab_record["sourceTitle"],
            )
            return None

        try:
            download_item = self.download_client.add_torrent(
                grab_record["data"]["downloadUrl"],
                paused=True,
                download_dir=str(self.seeding_dir),
            )
        except transmission_rpc.error.TransmissionError:  # pragma: no cover
            # Tolerate exceptions adding torrents because the download
            # URL may no longer be valid, IOW 404:
            logger.exception(
                "Exception adding torrent: %s",
                grab_record["sourceTitle"],
            )
            return None

        download_items_by_id[download_item.hashString.upper()] = download_item
        return download_item


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
