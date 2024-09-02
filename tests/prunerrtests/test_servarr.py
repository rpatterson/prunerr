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
