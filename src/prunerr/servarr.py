"""
Prunerr interaction with Servarr instances.
"""

import dataclasses
import time
import urllib.parse
import logging

import arrapi
import arrapi.apis.base

import prunerr.downloadclient
import prunerr.downloaditem
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
        },
        "radarr": {
            "dir_type": "movie",
            "item_type": "movie",
            "file_has_multi": False,
            "client": arrapi.RadarrAPI,
            "download_dir_field": "movieDirectory",
            "rename_template": "{movie[title]} ({movie[release_year]})",
        },
    }
    MAX_PAGE_SIZE = 250

    config = None
    client = None
    queue = None

    def __init__(self, runner):
        """
        Capture a references to the runner and individual Servarr configuration.
        """
        self.runner = runner
        self.download_clients = {}

    def __repr__(self):
        """
        Readable, informative, and specific representation to ease debugging.
        """
        return f"<{type(self).__name__} {self.config['name']!r}>"

    def update(self, config):
        """
        Update configuration, connect the API client, and refresh Servarr API data.

        Also retrieves any download clients defined in the Servarr settings and updates
        the prunerr representations.
        """
        self.config = config

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
            ):  # pragma: no cover
                # BBB: Why misidentified as not covered under Python 3.9?
                continue
            download_client_config = deserialize_servarr_download_client(
                download_client_config,
            )
            # Instantiate newly defined download clients
            download_clients[
                download_client_config["url"]
            ] = PrunerrServarrDownloadClient(self)
            download_clients[download_client_config["url"]].update(
                download_client_config
            )
        self.download_clients = download_clients

        # Update any data in instance state that should *not* be cached across updates
        self.queue = {
            record["downloadId"]: dict(record, servarr=self)
            for record in self.get_api_paged_records("queue")
            # `Pending` records have no download client hash yet
            if record.get("downloadId")
        }

        return self.client

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
            yield from response["records"]


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
    if "port" in download_client_config["fieldValues"]:
        netloc = f"{netloc}:{download_client_config['fieldValues']['port']}"
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
