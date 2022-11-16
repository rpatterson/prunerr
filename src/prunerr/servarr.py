"""
Prunerr interaction with Servarr instances.
"""

import os
import dataclasses
import datetime
import urllib.parse
import pathlib
import functools
import itertools
import json
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
    # Map Servarr event types to download client location path config
    EVENT_LOCATIONS = dict(
        grabbed=dict(src="downloadDir", dst="downloadDir"),
        downloadFolderImported=dict(src="downloadDir", dst="seedingDir"),
        downloadIgnored=dict(src="downloadDir", dst="seedingDir"),
        downloadFailed=dict(src="downloadDir", dst="seedingDir"),
        fileDeleted=dict(src="seedingDir", dst="seedingDir"),
    )
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
            "Connecting to Servarr instance: %s",
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
            "Requesting Servarr download clients settings: %r",
            self.config["name"],
        )
        for download_client_config in self.client.get("downloadclient"):
            if not download_client_config["enable"]:
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
                (record["downloadId"], record) for record in page["records"]
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

    def get_api_paged_records(self, endpoint):
        """
        Yield each page of the given paged endpoint until exhausted.

        Useful to continue only as far as needed in a large data set, such as Servarr
        history, but also useful to conveniently get all pages of a smaller data set.
        """
        response = {}
        page_number = 1
        while (
            # First page, no response yet
            not response
            # Is history for this Servarr instance exhausted?
            or (page_number * 250) <= response["totalRecords"]
        ):
            logger.debug(
                "Requesting Servarr page %s: %s/api/v3/%s",
                page_number,
                self.config["name"],
                endpoint,
            )
            response = self.client.get(
                endpoint,
                # Maximum Servarr page size
                pageSize=self.MAX_PAGE_SIZE,
                page=page_number,
            )
            page_number = response["page"]
            yield response

    def get_dir_history(self, dir_id):
        """
        Retreive and collate the history for the given series/movie/etc..
        """
        if dir_id in self.history["dirs"]:
            return self.history["dirs"][dir_id]

        type_map = self.TYPE_MAPS[self.config["type"]]
        params = {f"{type_map['dir_type']}id": dir_id}
        logger.debug(
            "Requesting %r Servarr media directory history: %s",
            self.config["name"],
            json.dumps(params),
        )
        history_response = self.client.get(
            f"history/{type_map['dir_type']}",
            **params,
        )
        self.history["dirs"][dir_id] = self.collate_history_records(
            history_records=history_response,
        )
        return self.history["dirs"][dir_id]

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
        for history_page in self.get_api_paged_records("history"):
            self.collate_history_records(
                history_records=history_page["records"],
            )
            download_record, indexer_record = self.get_item_history_records(
                download_item,
            )
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
    download_item_dirs = None

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
        self.download_item_dirs = {
            "downloadDir": pathlib.Path(
                self.config["fieldValues"][
                    self.servarr.TYPE_MAPS[self.servarr.config["type"]][
                        "download_dir_field"
                    ]
                ]
            ).resolve(),
        }

        return self.download_item_dirs

    def sync(self):
        """
        Synchronize the state of download client items with Servarr event history.
        """
        sync_results = {}
        for download_item in self.download_client.items:
            # Wrap the inner loop so that exceptions can be logged and the rest of the
            # items still synced
            try:
                item_result = self.sync_item(download_item)
            except ServarrTODOException:
                logger.exception(
                    "Un-handled exception syncing item: %s",
                    download_item.name,
                )
                if "DEBUG" in os.environ:
                    raise
                continue
            if item_result is not None:
                sync_results[download_item.name] = item_result
        return sync_results

    def get_item_servarr_dir(self, download_item):
        """
        Determine if this download item is managed by this Servarr instance.
        """
        for servarr_dir in self.download_item_dirs.values():
            if servarr_dir in download_item.path.parents:
                logger.debug(
                    "Download item %r is managed by Servarr: %s",
                    download_item,
                    self.config["name"],
                )
                break
        else:
            logger.debug(
                "Download item %r not managed by Servarr: %s",
                download_item,
                self.config["name"],
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
        if not self.download_client.runner.replay:
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
                    "No %r Servarr history found, skipping: %r",
                    self.servarr.config["name"],
                    download_item,
                )
                return download_item.serialize_download_data()
            dir_id = download_record[dir_id_key]

        if dir_id:
            download_item.prunerr_data["dirId"] = dir_id
        return dir_id

    def sync_item(self, download_item):
        """
        Ensure the download item state is in sync with Servarr state.
        """
        # TODO: Observed items being moved back and forth.  Investigate and fix.
        if not self.get_item_servarr_dir(download_item):
            if not self.download_client.runner.quiet:
                logger.debug(
                    "Download item not managed by Servarr %r: %s",
                    self.servarr.config["name"],
                    download_item.name,
                )
            return None
        download_path = download_item.path
        download_item.prunerr_data["servarr"].update(self.servarr.config)
        dir_id = self.get_item_dir_id(download_item)
        if dir_id is None:
            return None

        # Replace the history in the Prunerr data file with the canonical Servarr
        # history now that we have the item's Servarr directory (e.g. Sonarr/Radarr
        # series/movie) DB id.  Preserve additional Prunerr data where present.
        existing_history = download_item.prunerr_data["history"]
        download_item.prunerr_data["history"] = {}
        dir_history = self.servarr.get_dir_history(dir_id)
        if (
            download_item.hashString.lower()
            not in dir_history["records"]["download_ids"]
        ):
            logger.info(
                "Waiting for %r Servarr history:  %r",
                self.servarr.config["name"],
                download_item,
            )
            # Continue to below to write item Prunerr data
        seen_event_types = set()
        for history_record in reversed(
            dir_history["records"]["download_ids"].get(
                download_item.hashString.lower(),
                [],
            ),
        ):
            # TODO: Skip duplicate events for multi-file items such as season packs
            self.sync_item_history_record(
                download_item,
                seen_event_types,
                existing_history,
                history_record,
            )

        # If no indexer was found in the Servarr history,
        # try to match by the tracker URLs
        if "indexer" not in download_item.prunerr_data:
            download_item.prunerr_data["indexer"] = download_item.match_indexer_urls()

        # Update Prunerr JSON data file, after the handler has run to allow it to update
        # history record prunerr data.
        download_item.serialize_download_data(download_item.prunerr_data["history"])

        if download_item.path != download_path:
            return str(download_item.path)

        return None

    def sync_item_history_record(
        self,
        download_item,
        seen_event_types,
        existing_history,
        history_record,
    ):
        """
        Sync download item state with an individual Servarr history record.
        """
        # Preserve existing Prunerr data
        existing_record = {}
        if existing_history is not None:
            existing_record = existing_history.get(history_record["date"], {})
        history_record["prunerr"] = existing_record.get("prunerr", {})
        # Insert into the new history keyed by time stamp
        download_item.prunerr_data["history"][history_record["date"]] = history_record
        if "indexer" in history_record["data"]:
            # Cache indexer name for faster lookup
            download_item.prunerr_data.setdefault(
                "indexer",
                history_record["data"]["indexer"],
            )

        # Avoid redundant operations, such as when a download item contains multiple
        # imported files: e.g. Sonarr season packs.
        if not self.download_client.runner.replay and history_record["prunerr"].get(
            "syncedDate"
        ):
            if history_record["eventType"] not in seen_event_types:
                seen_event_types.add(history_record["eventType"])
                logger.debug(
                    "Previously synced %r event: %r",
                    history_record["eventType"],
                    download_item,
                )
            return None

        # Synchronize the item's state with this history event/record
        # Run any handler for this specific event type, if defined
        handler = getattr(
            self,
            f"handle_{history_record['eventType']}",
            self.sync_item_location,
        )
        logger.debug(
            "Handling %r Servarr %r event: %r",
            self.servarr.config["name"],
            history_record["eventType"],
            download_item,
        )
        handler_result = handler(
            download_item,
            history_record,
        )
        if handler_result is not None:
            history_record["prunerr"]["handlerResult"] = str(handler_result)
            history_record["prunerr"]["syncedDate"] = datetime.datetime.now()

        return handler_result

    def sync_item_location(self, download_item, history_record):
        """
        Ensure the download item location matches its Servarr state.
        """
        event_locations = self.servarr.EVENT_LOCATIONS[history_record["eventType"]]

        src_path = self.download_item_dirs[event_locations["src"]]
        dst_path = self.download_item_dirs[event_locations["dst"]]
        if dst_path in download_item.path.parents:
            logger.debug(
                "Download item %r already in correct location: %r",
                download_item,
                str(download_item.path),
            )
            return str(download_item.path)

        if src_path not in download_item.path.parents:
            event_paths = set()
            for other_event_locations in self.servarr.EVENT_LOCATIONS.values():
                event_paths.update(other_event_locations.values())
            for event_path in event_paths:
                if self.servarr.config[event_path] in download_item.path.parents:
                    logger.warning(
                        "Download item %r not in correct managed dir, %r: %r",
                        download_item,
                        str(src_path),
                        str(download_item.path),
                    )
                    src_path = self.servarr.config[event_path]
                    break
            else:
                logger.error(
                    "Download item %r not in a managed dir: %r",
                    download_item,
                    str(download_item.path),
                )
                return str(download_item.path)

        if not download_item.files():
            logger.warning(
                "Download item has no files yet: %r",
                download_item,
            )
            return None

        return download_item.move(dst_path)

    def handle_downloadFolderImported(  # pylint: disable=invalid-name
        self,
        download_item,
        history_record,
    ):
        """
        Handle Servarr imported event, wait for import to complete, then move.
        """
        download_data = download_item.prunerr_data
        if "latestImportedDate" not in download_data:
            download_data["latestImportedDate"] = history_record["date"]
        wait_duration = (
            datetime.datetime.now(download_data["latestImportedDate"].tzinfo)
            - download_data["latestImportedDate"]
        )
        if wait_duration < self.servarr.HISTORY_WAIT:
            logger.info(
                "Waiting for import to complete before moving, %s so far: %r",
                wait_duration,
                download_item,
            )
            return None
        if not self.servarr.runner.replay:
            imported_records = [
                imported_record
                for imported_record in download_data["history"].values()
                if imported_record["eventType"] == "downloadFolderImported"
            ]
            if imported_records:
                logger_level = logger.debug
            else:
                logger_level = logger.error
            logger_level(
                "Found %s imported history records after %s for %r",
                len(imported_records),
                wait_duration,
                download_item,
            )

        # If we're not waiting for history, then proceed to move the download item.
        # Ensure the download item's location matches the Servarr state.
        history_record["prunerr"]["handlerResult"] = str(
            self.sync_item_location(download_item, history_record),
        )

        # Reflect imported files in the download client item using symbolic links
        old_dropped_path = pathlib.Path(history_record["data"]["droppedPath"])
        if self.download_item_dirs["downloadDir"] not in old_dropped_path.parents:
            logger.warning(
                "Servarr dropped path %r not in download client's download directory %r"
                "for %r",
                history_record["data"]["droppedPath"],
                self.download_item_dirs["downloadDir"],
                download_item,
            )
            return download_item
        relative_to_download_dir = old_dropped_path.relative_to(
            self.download_item_dirs["downloadDir"],
        )
        new_dropped_path = download_item.downloadDir / relative_to_download_dir
        link_path = new_dropped_path.parent / (
            f"{new_dropped_path.stem}"
            f"{download_item.download_client.SERVARR_IMPORTED_LINK_SUFFIX}"
        )
        imported_link_target = pathlib.Path(
            os.path.relpath(history_record["data"]["importedPath"], link_path.parent)
        )
        if os.path.lexists(link_path):
            if not link_path.is_symlink():
                logger.error(
                    "Imported file link is not a symlink: %s",
                    link_path,
                )
            elif pathlib.Path(os.readlink(link_path)) != imported_link_target:
                logger.error(
                    "Download file symlink to wrong imported file: %s -> %s",
                    link_path,
                    imported_link_target,
                )
        elif not link_path.parent.exists():
            logger.error(
                "Imported file link directory no longer exists: %s",
                link_path,
            )
        else:
            logger.info(
                "Symlinking imported file: %s -> %s",
                link_path,
                imported_link_target,
            )
            if not (link_path.parent / imported_link_target).is_file():
                logger.error(
                    "Symlink download file to imported file that doesn't exist: "
                    "%s -> %s",
                    link_path,
                    imported_link_target,
                )
            link_path.symlink_to(imported_link_target)

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


PREVIOUSLY_SYNCED_EVENT_RESULT = object()


class ServarrTODOException(Exception):
    """
    Placeholder exception until we can determine the correct, narrow list of exceptions.
    """
