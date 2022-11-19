"""
Prunerr interaction with Servarr instances.
"""

import dataclasses
import time
import datetime
import urllib.parse
import pathlib
import functools
import itertools
import logging

import arrapi
import arrapi.apis.base

import prunerr.utils
import prunerr.downloadclient
import prunerr.downloaditem

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
    TYPE_MAPS = dict(
        sonarr=dict(
            # The top-level containing type, if applicable.  IOW, the type of items in
            # the top-level listing of the Servarr UI.  This is series for Sonarr as
            # contrasted with episode or season.  This is movie for Radarr.
            dir_type="series",
            # File vs item is a little confusing.  Item refers to episodes/movies as
            # contrasted with the `dir_type`.  But an episode/movie may comprise of
            # multiple files and a file may contain multiple episodes.
            item_type="episode",
            file_has_multi=True,
            client=arrapi.SonarrAPI,
            download_dir_field="tvDirectory",
            rename_template=(
                "{series[title]} - {episode[seasonEpisode]} - {episode[title]}"
            ),
        ),
        radarr=dict(
            dir_type="movie",
            item_type="movie",
            file_has_multi=False,
            client=arrapi.RadarrAPI,
            download_dir_field="movieDirectory",
            rename_template="{movie[title]} ({movie[release_year]})",
        ),
    )
    EVENT_TYPES = {
        "grabbed": 1,
        "downloadFolderImported": 3,
        "downloadIgnored": 7,
        "downloadFailed": 4,
        "fileDeleted": 5,
        "fileRenamed": 6,
    }
    MAX_PAGE_SIZE = 250
    # Number of seconds to wait for new file import history records to appear in Servarr
    # history.  This should be the maximum amount of time it might take to import a
    # single file in the download client item, not necessarily the entire item.  Imagine
    # how long might it take Sonarr to finish importing a download client item when:
    #
    # - Sonarr is configured to copy rather than making hard links
    # - the host running Sonarr is under high load
    # - the RAID array is being rebuilt
    # - etc.
    # TODO: Move to config
    HISTORY_WAIT = datetime.timedelta(seconds=120)

    config = None
    client = None
    queue = None

    def __init__(self, runner):
        """
        Capture a references to the runner and individual Servarr configuration.
        """
        self.runner = runner
        self.download_clients = {}

        # Initialize any data cached in instance state across updates
        self.history = dict(
            page=0,
            records=dict(download_ids={}, source_titles={}),
            event_types=dict(download_ids={}, source_titles={}),
            dirs={},
        )

    def __repr__(self):
        """
        Readable, informative, and specific representation to ease debugging.
        """
        return f"<{type(self).__name__} {self.config['name']!r}>"

    def update(self, config=None):
        """
        Update configuration, connect the API client, and refresh Servarr API data.

        Also retrieves any download clients defined in the Servarr settings and updates
        the prunerr representations.
        """
        if config is not None:
            self.config = config
        if self.config is None:
            raise ValueError("No Servarr configuration provided")

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
        logger.debug(
            "Requesting %s download clients settings",
            self.config["name"],
        )
        for download_client_config in self.client.get("downloadclient"):
            if (
                not download_client_config["enable"]
                or download_client_config["implementation"] != "Transmission"
            ):
                continue
            download_client_config = deserialize_servarr_download_client(
                download_client_config,
            )
            if download_client_config["url"] in self.download_clients:
                # Preserve any cached state in existing download clients
                download_clients[download_client_config["url"]] = self.download_clients[
                    download_client_config["url"]
                ]
            else:
                # Instantiate newly defined download clients
                download_clients[
                    download_client_config["url"]
                ] = PrunerrServarrDownloadClient(self)
            download_clients[download_client_config["url"]].update(
                download_client_config
            )
        self.download_clients = download_clients

        # Update any data in instance state that should *not* be cached across updates
        self.queue = {}
        for page in self.get_api_paged_records("queue"):
            self.queue.update(
                (record["downloadId"], record)
                for record in page["records"]
                # `Pending` records have no download client hash yet
                if record.get("downloadId")
            )

        return self.client

    def strip_type_prefix(self, prefixed, servarr_term="item_type"):
        """
        Strip the particular Servarr type prefix if present.
        """
        # Map the different Servarr applications type terminology
        servarr_type_map = self.TYPE_MAPS[self.config["type"]]
        prefix = servarr_type_map[servarr_term]
        if prefixed.startswith(prefix):
            stripped = prefixed[len(prefix) :]
            stripped = f"{stripped[0].lower()}{stripped[1:]}"
            # Don't strip the prefix for DB IDs in the Servarr API JSON, e.g.:
            # `movieId`.
            if stripped != "id":
                return stripped

        return prefixed

    def get_api_paged_records(self, endpoint, page_number=1, **params):
        """
        Yield each page of the given paged endpoint until exhausted.

        Useful to continue only as far as needed in a large data set, such as Servarr
        history, but also useful to conveniently get all pages of a smaller data set.
        """
        response = {}
        while (
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
            response = self.client.get(
                endpoint,
                # Maximum Servarr page size
                pageSize=self.MAX_PAGE_SIZE,
                page=page_number,
                **params,
            )
            page_number = response["page"] + 1
            yield response

    def find_item_latest_global_history(self, download_item):
        """
        Find the most recent global Servarr history record for the given download item.

        If the item is in a Servarr managed directory but not managed by Servarr then
        there may be no global history for the item.  In that case, this call will page
        through all the global Servarr history.

        Cache these lookups as we page through the history across subsequent calls.
        """
        # TODO: Check for new history since last call
        download_record, indexer_record = self.get_item_history_records(download_item)
        history_page = None
        for event_type in ("grabbed", "downloadFolderImported"):
            for history_page in self.get_api_paged_records(
                "history",
                page_number=self.history["page"] + 1,
                eventType=self.EVENT_TYPES[event_type],
            ):
                self.collate_history_records(
                    history_records=history_page["records"],
                )
                self.history["page"] = history_page["page"]
                download_record, indexer_record = self.get_item_history_records(
                    download_item,
                )
                if indexer_record is not None:
                    break
            if indexer_record is not None:
                break

        return indexer_record if indexer_record is not None else download_record

    def get_item_history_records(self, download_item):
        """
        Check the cached API history for the item's identifying records.

        Return the `grabbed` event record and the best record that includes the indexer.
        """
        download_record = indexer_record = None
        for history_record in self.history["records"]["download_ids"].get(
            download_item.hashString.lower(),
            [],
        ):
            if "downloadId" in history_record:
                if download_record is None:
                    # Sufficient to identify download client item, fallback
                    download_record = history_record
                if "indexer" in history_record["data"]:
                    # Can also identify the indexer, optimal
                    indexer_record = history_record
                    break
        return download_record, indexer_record

    def collate_history_records(self, history_records):
        """
        Collate Servarr history response under best ids for each history record.
        """
        # TODO: Can cached Servarr history become stale?  IOW, does Servarr history
        # every delete or otherwise change/mutate?
        for history_record in history_records:
            prunerr.utils.deserialize_history(history_record)
            for history_data in (history_record, history_record["data"]):
                for key, value in list(history_data.items()):
                    # Normalize specific values using Servarr type-specific prefixes
                    if key == "eventType":
                        history_data[key] = self.strip_type_prefix(value)
                    # Normalize keys using prefixes specific to the Servarr type
                    key_stripped = self.strip_type_prefix(key)
                    history_data[key_stripped] = history_data.pop(key)

            # Collate history under the best available identifier that may be
            # matched to download client items
            if "downloadId" in history_record:
                # History record can be matched exactly to the download client item
                self.history["records"]["download_ids"].setdefault(
                    history_record["downloadId"].lower(),
                    [],
                ).append(history_record)
                self.history["event_types"]["download_ids"].setdefault(
                    history_record["downloadId"].lower(),
                    {},
                ).setdefault(history_record["eventType"], []).append(history_record)
            if "importedPath" in history_record["data"]:
                # Capture a reference that may match to more recent history record
                # below, such as deleting upon upgrade
                self.history["records"]["source_titles"].setdefault(
                    history_record["data"]["importedPath"],
                    [],
                ).append(history_record)
                self.history["event_types"]["source_titles"].setdefault(
                    history_record["data"]["importedPath"],
                    {},
                ).setdefault(history_record["eventType"], []).append(history_record)
            if "sourceTitle" in history_record:
                # Can't match exactly to a download client item, capture a reference
                # that may match to more recent history record below, such as
                # deleting upon upgrade
                self.history["records"]["source_titles"].setdefault(
                    history_record["sourceTitle"],
                    [],
                ).append(history_record)
                self.history["event_types"]["source_titles"].setdefault(
                    history_record["sourceTitle"],
                    {},
                ).setdefault(history_record["eventType"], []).append(history_record)

            # Match this older import history record to previously processed, newer,
            # records that don't match exactly to a download client item, such as
            # deleting upon upgrade
            if (
                "downloadId" in history_record
                and "importedPath" in history_record["data"]
                and history_record["data"]["importedPath"]
                in self.history["records"]["source_titles"]
            ):
                # Insert previous, newer history records under the download id that
                # matches the import path for this older record
                source_titles = self.history["records"]["source_titles"][
                    history_record["data"]["importedPath"]
                ]
                download_records = self.history["records"]["download_ids"][
                    history_record["downloadId"].lower()
                ]
                latest_download_record = download_records[0]
                newer_records = list(
                    itertools.takewhile(
                        functools.partial(is_record_newer, latest_download_record),
                        source_titles,
                    )
                )
                download_records[:0] = newer_records
                # Do the same for each even type
                newer_event_types = {}
                for newer_record in newer_records:
                    newer_event_types.setdefault(
                        newer_record["eventType"],
                        [],
                    ).append(newer_record)
                for (
                    event_type,
                    newer_event_records,
                ) in newer_event_types.items():
                    self.history["event_types"]["download_ids"][
                        history_record["downloadId"].lower()
                    ].setdefault(event_type, [])[:0] = newer_event_records

                # Also include history records under the imported path
                self.history["records"]["source_titles"].setdefault(
                    history_record["data"]["importedPath"],
                    [],
                ).append(history_record)
                self.history["event_types"]["source_titles"].setdefault(
                    history_record["data"]["importedPath"],
                    {},
                ).setdefault(history_record["eventType"], []).append(history_record)

        return self.history


class PrunerrServarrDownloadClient:
    """
    A specific Servar instance's individual specific download client.
    """

    config = None
    download_client = None
    download_dir = None
    seeding_dir = None

    def __init__(self, servarr):
        """
        Capture a references to the servarr instance and download client.
        """
        self.servarr = servarr

    def __repr__(self):
        """
        Readable, informative, and specific representation to ease debugging.
        """
        return (
            f"<{type(self).__name__} {self.servarr.config['name']!r}"
            f"->{self.download_client.config['url']!r}>"
        )

    def update(self, config=None):
        """
        Reconcile Prunerr and Servarr download client configurations and update data.
        """
        if config is not None:
            self.config = config
        if self.config is None:
            raise ValueError("No Servarr configuration provided")

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
        download directory, and aren't in this Servarr instance's queue.
        """
        download_items = [
            download_item
            for download_item in self.download_client.items
            if download_item.status == "seeding"
            and download_item.hashString.upper() not in self.servarr.queue
            and self.download_dir in download_item.path.parents
        ]
        if not download_items:
            logger.debug(
                "No %s download items to move",
                self.servarr.config["name"],
            )
            return None
        logger.info(
            "Moving download items: %r -> %r\n  %s",
            self.download_dir,
            self.seeding_dir,
            "\n  ".join(repr(download_item) for download_item in download_items),
        )
        self.download_client.client.move_torrent_data(
            ids=[download_item.hashString for download_item in download_items],
            location=self.seeding_dir,
        )
        # Wait for a timeout for items to finish moving before proceeding.
        start = time.time()
        while next(
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
        return download_items

    def get_item_servarr_dir(self, download_item):
        """
        Determine if this download item is managed by this Servarr instance.
        """
        for servarr_dir in (self.download_dir, self.seeding_dir):
            if servarr_dir in download_item.path.parents:
                logger.debug(
                    "Download item is managed by %s: %r",
                    self.servarr.config["name"],
                    download_item,
                )
                break
        else:
            logger.debug(
                "Download item not managed by %s: %r",
                self.servarr.config["name"],
                download_item,
            )
            return None
        download_item.prunerr_data.setdefault("servarr", {})
        if (
            "url" in download_item.prunerr_data["servarr"]
            and download_item.prunerr_data["servarr"].get("url")
            != self.servarr.config["url"]
        ):
            raise NotImplementedError(
                f"Item download dir matches Servarr {self.servarr.config['name']!r} "
                "but item data if for Servarr "
                f"{download_item.prunerr_data['servarr']['name']!r}."
            )
        return servarr_dir

    def get_item_dir_id(self, download_item):
        """
        Find the item's Servarr directory (e.g. Sonarr/Radarr series/movie) DB id.

        Try to do so in the most efficient way possible:
        1. Cached in the Prunerr data file
        2. From the Servarr queue API while still downloading
        3. As a last resort, search the whole Servarr history
        """
        dir_id_key = (
            f"{self.servarr.TYPE_MAPS[self.servarr.config['type']]['dir_type']}Id"
        )
        dir_id = None
        # Get from existing Prunerr item data if available.
        # First from the Servarr queue records if Prunerr was able to get those
        # records before the item finished downloading.
        dir_id = download_item.prunerr_data.get("queue", {}).get(dir_id_key)
        # Otherwise, try to get it from the item's Servarr history records
        if dir_id is None and download_item.prunerr_data.get("history"):
            for history_record in reversed(
                download_item.prunerr_data["history"].values(),
            ):
                if dir_id_key in history_record:
                    dir_id = history_record.get(dir_id_key)
                    break
        if dir_id is None:
            # Optimally, identify the item in the Servarr queue if still downloading
            queue = self.servarr.queue.get(download_item.hashString.upper(), {})
            if queue:
                dir_id = queue[dir_id_key]
                download_item.prunerr_data["queue"] = queue
                if queue.get("indexer"):
                    download_item.prunerr_data.setdefault(
                        "indexer",
                        queue.get("indexer"),
                    )
        if dir_id is None:
            # As a last result, search the global Servarr history
            download_record = self.servarr.find_item_latest_global_history(
                download_item,
            )
            if download_record is None:
                logger.error(
                    "No %s history found, skipping: %r",
                    self.servarr.config["name"],
                    download_item,
                )
                return download_item.serialize_download_data()
            dir_id = download_record[dir_id_key]
            if download_record["data"].get("indexer"):
                download_item.prunerr_data.setdefault(
                    "indexer",
                    download_record["data"]["indexer"],
                )

        if dir_id:
            download_item.prunerr_data["dirId"] = dir_id
        return dir_id


def deserialize_servarr_download_client(download_client_config):
    """
    Assemble field values and a URL for a Servarr download client configuration.
    """
    download_client_config["fieldValues"] = {
        download_client_config_field["name"]: download_client_config_field["value"]
        for download_client_config_field in download_client_config["fields"]
        if "value" in download_client_config_field
    }
    netloc = (
        f"{download_client_config['fieldValues']['host']}:"
        f"{download_client_config['fieldValues']['port']}"
    )
    if download_client_config["fieldValues"].get("username"):
        if download_client_config["fieldValues"].get("password"):
            netloc = (
                f"{download_client_config['fieldValues']['username']}:"
                f"{download_client_config['fieldValues']['password']}@"
                f"{netloc}"
            )
        else:
            netloc = f"{download_client_config['fieldValues']['username']}@{netloc}"
    download_client_config["url"] = urllib.parse.SplitResult(
        "http" if not download_client_config["fieldValues"]["useSsl"] else "https",
        netloc,
        download_client_config["fieldValues"]["urlBase"],
        None,
        None,
    ).geturl()
    return download_client_config


def is_record_newer(comparison_record, test_record):
    """
    Return true if the test record's date is newer than the comparison record's date.

    Useful with `functools.partial` to use in `itertools.*` functions.
    """
    return test_record["date"] > comparison_record["date"]


class ServarrTODOException(Exception):
    """
    Placeholder exception until we can determine the correct, narrow list of exceptions.
    """
