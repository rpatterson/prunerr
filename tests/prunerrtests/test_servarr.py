# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Test Prunerr's interaction with Servarr instances.
"""

import os

from unittest import mock

import transmission_rpc

import prunerrtests

import prunerr


@mock.patch.dict(os.environ, prunerrtests.PrunerrTestCase.ENV)
class PrunerrServarrTests(
    prunerrtests.PrunerrTestCase,
):  # pylint: disable=too-few-public-methods
    """
    Test Prunerr's interaction with Servarr instances.
    """

    def test_servarr_repr(self):
        """
        The Servarr representations provide useful information for debugging.
        """
        runner = prunerr.runner.PrunerrRunner(config=self.CONFIG)
        runner.config = {}
        servarr = prunerr.servarr.PrunerrServarrInstance(runner)
        servarr.config = {"name": list(self.config["servarrs"].keys())[0]}
        self.assertIn(
            servarr.config["name"],
            repr(servarr),
            "Servarr name missing from Servarr representation",
        )
        servarr_download_client = prunerr.servarr.PrunerrServarrDownloadClient(servarr)
        servarr_download_client.download_client = (
            prunerr.downloadclient.PrunerrDownloadClient(runner)
        )
        servarr_download_client.config = {
            "url": self.download_client_urls[0],
        }
        servarr_download_client.download_dir = self.downloaded_item.parent
        servarr_download_client.download_client.servarrs = {
            servarr_download_client.download_dir: servarr_download_client
        }
        servarr_download_client.download_client.items = [
            prunerr.downloaditem.PrunerrDownloadItem(
                servarr_download_client.download_client,
                None,
                transmission_rpc.Torrent(
                    None,
                    {
                        "id": list(self.download_client_items_responses.values())[0][
                            "arguments"
                        ]["torrents"][0]["hashString"],
                        "name": self.download_item_title,
                        "sizeWhenDone": 1,
                        "downloadDir": str(servarr_download_client.download_dir),
                    },
                ),
            )
        ]
        servarr_download_client.download_client.operations = (
            prunerr.operations.PrunerrOperations(
                servarr_download_client.download_client,
                {},
            )
        )
        self.assertIn(
            servarr.config["name"],
            repr(servarr_download_client),
            "Servarr name missing from Servarr representation",
        )
        self.assertIn(
            self.download_client_urls[0],
            repr(servarr_download_client),
            "Download client URL missing from Servarr representation",
        )
        self.assertIn(
            self.download_item_title,
            repr(servarr_download_client.download_client.items[0].release),
            "Download item title missing from Servarr release representation",
        )
