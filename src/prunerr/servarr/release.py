# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

# pylint: disable=magic-value-comparison,missing-any-param-doc,missing-param-doc
# pylint: disable=missing-raises-doc,missing-return-doc,missing-return-type-doc
# pylint: disable=missing-type-doc,missing-yield-doc,missing-yield-type-doc

"""
Prunerr interaction with Servarr instances.
"""

import logging

from .. import utils
from ..utils import cached_property

logger = logging.getLogger(__name__)


class PrunerrServarrRelease(utils.PrunerrComponent):
    """
    A specific Servar instance's individual download item.
    """

    download_item = None

    def __init__(self, servarr_download_client, download_item):
        """
        Capture references to the servarr download client and the download item.
        """
        self.servarr_download_client = servarr_download_client
        self.download_item = download_item

    @cached_property
    def details(self):
        """
        Assemble all available useful information.
        """
        return {
            "servarr": self.servarr_download_client.servarr.config.get("name"),
            "dowload_client": self.servarr_download_client.config.get("url"),
            "torrent": self.download_item,
        }

    @cached_property
    def queue(self):
        """
        Lookup this release's queue record from it's Servarr instance.
        """
        return self.servarr_download_client.servarr.queue.get(
            self.download_item.hashString.upper(),
        )

    @cached_property
    def history(self):
        """
        Lookup and collate this download item's Servarr history records.
        """
        return list(
            self.servarr_download_client.servarr.get_api_paged_records(
                "history",
                downloadId=self.download_item.hashString.upper(),
            ),
        )
