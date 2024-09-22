# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT


"""
Prunerr interaction with Servarr instances.
"""

import logging

from .. import utils
from ..utils import pathlib
from ..utils import cached_property
from . import history as history_module

logger = logging.getLogger(__name__)


class PrunerrServarrRootItem(utils.PrunerrComponent):
    """
    Prunerr's view of a root Servarr item, for example a series or movie.

    As opposed to a file item, for example an episode under Sonarr. Under Radarr these
    are the same.
    """

    def __init__(self, servarr, root_id):
        """
        Capture references to the servarr instance and root item DB ID.
        """
        self.servarr = servarr
        self.root_id = root_id
        self.params = {f"{servarr.type_map['dir_type']}Id": root_id}

    @property
    def details(self) -> dict:
        """
        Assemble all available useful information.

        :return: Map descriptive names to useful values.
        """
        details = {"id": self.root_id}
        if vars(self).get("data"):
            details["title"] = self.data["title"]
            details["year"] = self.data["year"]
        return details

    @cached_property
    def data(self) -> dict:
        """
        Retrieve the movie/series data from the Servarr JSON API.

        :return: The Servarr API JSON object representing this movie/series.
        """
        return self.servarr.dir_items[self.root_id]

    @cached_property
    def imported_items(self) -> dict:
        """
        Get and collate Servarr imported items and their files.

        :return: Map imported item, for example episode or movie, IDs to the Servarr API
            JSON for the item and it's file.
        """
        # Many of the Sonarr use cases for mapping imported files to download items will
        # do so for multiple imported episode files, for example season packs. There is
        # definitely significant overhead for multiple Servarr API requests, so request
        # **all** imported files for the series and cache them until measurement shows
        # that doing so causes significantly more overhead than requesting them
        # individually for a significant number of use cases. Note that this has no
        # effect for Radarr movies, because it's almost always one file so the request
        # count doesn't change either way.

        # Map item file IDs for correlating to the items:
        item_files = {
            item_file["id"]: item_file
            for item_file in self.servarr.client.get(
                f"{self.servarr.type_map['item_type']}File",
                **self.params,
            )
        }
        # Is there a 2nd level to get to files, for example series -> episode ->
        # file as opposed to just movie -> file:
        items = (
            [self.servarr.dir_items[self.root_id]]
            if self.servarr.type_map["file_depth"] == 1
            else self.servarr.client.get(
                self.servarr.type_map["item_type"],
                **self.params,
            )
        )
        # Then iterate over the imported files:
        imported_items = {}
        for imported_item in items:
            if not imported_item["hasFile"] is True:
                continue
            imported_item["file"] = item_files[
                imported_item[f"{self.servarr.type_map['item_type']}FileId"]
            ]
            imported_item["file"]["path"] = pathlib.Path(
                imported_item["file"]["path"],
            )
            imported_item["file"]["relative"] = imported_item["file"][
                "path"
            ].relative_to(
                imported_item["file"]["path"].parents[
                    self.servarr.type_map["file_depth"] - 1
                ]
            )
            imported_items[imported_item["id"]] = imported_item
        return imported_items

    @cached_property
    def history(self) -> history_module.PrunerrServarrHistory:
        """
        Map grab and import history records to download items by various means.

        :return: The Prunerr representation of what it needs from Servarr history.
        """
        history = history_module.PrunerrServarrHistory(self)
        history.update()
        return history
