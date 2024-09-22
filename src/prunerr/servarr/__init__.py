# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Prunerr interaction with Servarr instances.
"""

import collections
import typing
import functools
import dataclasses
import logging

import requests
import arrapi
import arrapi.raws.base

from .. import utils
from ..utils import cached_property
from . import downloadclient
from . import rootitem

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PrunerrServarrAPIClient(arrapi.raws.base.BaseRawAPI):
    """
    Generic Servarr API client regardless of the Servarr application type.
    """

    system_status: dict

    # Isolate the private instance attributes linter ignores in one location:
    get = arrapi.raws.base.BaseRawAPI._get  # pylint: disable=protected-access
    delete = arrapi.raws.base.BaseRawAPI._delete  # pylint: disable=protected-access
    post = (  # noqa: V107
        arrapi.raws.base.BaseRawAPI._post  # pylint: disable=protected-access
    )
    put = (  # noqa: V107
        arrapi.raws.base.BaseRawAPI._put  # pylint: disable=protected-access
    )
    request = arrapi.raws.base.BaseRawAPI._request  # pylint: disable=protected-access

    def __init__(
        self,
        url: str,
        apikey: str,
        session: typing.Optional[requests.Session] = None,
    ) -> None:
        """
        Implement the base class abstract method.
        """
        super().__init__(url, apikey, session=session)

    def get_system_status(self) -> dict:
        """
        Capture the system status for identifying the Servarr application type.

        :return: The deserialized Servarr API JSON.
        """
        self.system_status = super().get_system_status()
        return self.system_status


class PrunerrServarrInstance(utils.PrunerrComponent):
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
    EVENT_TYPE_GRABBED = "grabbed"
    DOWNLOAD_CLIENT_IMPLEMENTATION_TRANSMISSION = "Transmission"

    def __init__(self, runner):
        """
        Capture references to the runner and individual Servarr configuration.
        """
        self.runner = runner
        self.type_map = None
        self.config = {}
        self.client = None
        self.download_clients = {}
        self.download_client_names = {}

    @property
    def details(self) -> dict:
        """
        Assemble all available useful information.

        :return: Map descriptive names to useful values.
        """
        return {"name": self.config.get("name")}

    def update(self, config: dict):  # type: ignore # pylint: disable=arguments-differ
        """
        Update configuration, connect the API client, and refresh Servarr API data.

        Also retrieves any download clients defined in the Servarr settings and update
        the prunerr representations.

        :param config: The configuration for this Servarr instance from the Prunerr
            configuration.
        """
        super().update()
        self.config = config
        self.config["url"] = utils.normalize_url(self.config["url"])

        logger.debug(
            "Connecting to %s",
            self.config["name"],
        )
        self.client = PrunerrServarrAPIClient(
            self.config["url"],
            self.config["api-key"],
        )
        self.type_map = self.TYPE_MAPS[
            self.client.system_status["appName"].strip().lower()
        ]

        download_clients = {}
        download_client_names = {}
        logger.debug(
            "Requesting %s download clients settings",
            self.config["name"],
        )
        for servarr_download_client in self.client.get("downloadclient"):
            if (
                not servarr_download_client["enable"]
                or servarr_download_client["implementation"]
                != self.DOWNLOAD_CLIENT_IMPLEMENTATION_TRANSMISSION
            ):
                # BBB: Why misidentified as not covered under Python 3.9?
                continue  # pragma: no cover
            download_client_config = downloadclient.deserialize_servarr_download_client(
                servarr_download_client,
            )
            # Instantiate newly defined download clients
            download_client_url = utils.normalize_url(download_client_config["url"])
            download_clients[download_client_url] = (
                downloadclient.PrunerrServarrDownloadClient(self)
            )
            download_clients[download_client_url].update(download_client_config)
            download_client_names[servarr_download_client["name"]] = download_clients[
                download_client_url
            ]
        self.download_clients = download_clients
        self.download_client_names = download_client_names

    @cached_property
    def dir_items(self) -> dict:
        """
        Retrieve all the series/movies in this Servarr instance.

        :return: Map the items' DB IDs to the Servarr API JSON data for each item.
        """
        return {
            dir_item["id"]: dir_item
            for dir_item in self.client.get(self.type_map["dir_type"])
        }

    @cached_property
    def queue(self) -> dict:
        """
        Retrieve the queue of downloading releases for this Servarr instance.

        :return: Map history record download item hash IDs to the de-serialized Servarr
            API ``queue`` endpoint JSON records.
        """
        queue: dict = {}
        for record in self.get_api_paged_records("queue"):
            record["servarr"] = self
            # `Pending` records have no download item hash ID yet and so are grouped
            # under `None`:
            queue.setdefault(record.get("downloadId"), []).append(record)
        return queue

    @functools.lru_cache(maxsize=None)  # pylint: disable=method-cache-max-size-none
    def get_root_item(self, root_id: int) -> rootitem.PrunerrServarrRootItem:
        """
        Instantiate and cache Prunerr's representation of a root.

        :param root_id: The DB ID of the root item in the Servarr API.
        :return: The instance of Pruner's representation.
        """
        return rootitem.PrunerrServarrRootItem(self, root_id)

    def get_api_paged_records(
        self,
        endpoint: str,
        page_number: int = 1,
        **params,
    ) -> collections.abc.Iterable:
        """
        Yield each page of the given paged endpoint until exhausted.

        Useful to continue only as far as needed in a large data set, such as Servarr
        history, but also useful to conveniently get all pages of a smaller data set.

        :param endpoint: The Servarr API endpoint to request.
        :param page_number: The page number to start with.
        :param params: Additional parameters to pass onto the Servarr API endpoint
            request.
        :return: Yield each record from each page until there are no more pages.
        """
        response: dict = {}
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
