# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Test Prunerr's interaction with Servarr instances.
"""

import os

from unittest import mock

import prunerrtests

import prunerr


@mock.patch.dict(os.environ, prunerrtests.PrunerrTestCase.ENV)
class PrunerrServarrTests(
    prunerrtests.PrunerrTestCase,
):  # pylint: disable=too-few-public-methods
    """
    Test Prunerr's interaction with Servarr instances.
    """

    RESPONSES_DIR = prunerrtests.PrunerrTestCase.RESPONSES_DIR.parent / "servarr"

    def test_servarr_repr(self):
        """
        The Servarr representations provide useful information for debugging.
        """
        runner = prunerr.runner.PrunerrRunner(config=self.CONFIG)
        self.mock_responses()
        runner.update()

        servarr = list(runner.servarrs.values())[0]
        self.assertIn(
            servarr.config["name"],
            repr(servarr),
            "Servarr name missing from Servarr representation",
        )
        servarr_download_client = list(servarr.download_clients.values())[0]
        self.assertIn(
            servarr.config["name"],
            repr(servarr_download_client),
            "Servarr name missing from Servarr representation",
        )
        self.assertIn(
            list(self.download_client_items_responses.keys())[0],
            repr(servarr_download_client),
            "Download client URL missing from Servarr representation",
        )
        self.assertIn(
            self.download_item_title,
            repr(servarr_download_client.download_client.items[0].release),
            "Download item title missing from Servarr release representation",
        )

        root_item = prunerr.servarr.rootitem.PrunerrServarrRootItem(servarr, 1)
        self.assertIn(
            "id=1",
            repr(root_item),
            "Series DB ID missing from Servarr representation",
        )
        self.assertIsInstance(
            root_item.data,
            dict,
            "Wrong root item data type",
        )
        self.assertTrue(
            root_item.data.get("title"),
            "Root item data missing series title",
        )
        self.assertIn(
            root_item.data["title"],
            repr(root_item),
            "Series title missing from Servarr representation",
        )

        self.assertIn(
            "root_item=",
            repr(root_item.history),
            "Series representation missing from Servarr history representation",
        )
