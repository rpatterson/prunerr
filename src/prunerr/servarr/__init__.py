# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

# pylint: disable=magic-value-comparison,missing-any-param-doc,missing-param-doc
# pylint: disable=missing-raises-doc,missing-return-doc,missing-return-type-doc
# pylint: disable=missing-type-doc,missing-yield-doc,missing-yield-type-doc

"""
Prunerr interaction with Servarr instances.
"""

import dataclasses
import logging

import arrapi
import arrapi.apis.base

from .. import utils
from ..utils import cached_property
from . import downloadclient

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

    @cached_property
    def details(self):
        """
        Assemble all available useful information.
        """
        return {"name": self.config.get("name")}

    def update(self, config):  # pylint: disable=arguments-differ
        """
        Update configuration, connect the API client, and refresh Servarr API data.

        Also retrieves any download clients defined in the Servarr settings and updates
        the prunerr representations.
        """
        super().update()
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

        return self.client

    @cached_property
    def queue(self):
        """
        Retrieve the queue of downloading releases for this Servarr instance.

        :return: Map The Servarr API JSON
        """
        queue = {}
        for record in self.get_api_paged_records("queue"):
            record["servarr"] = self
            # `Pending` records have no download item hash ID yet and so are grouped
            # under `None`:
            queue.setdefault(record.get("downloadId"), []).append(record)
        return queue

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
