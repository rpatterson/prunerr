# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Test Prunerr's configurable operations.
"""

import os
from unittest import mock

import prunerrtests

import prunerr.runner
import prunerr.downloadclient
import prunerr.downloaditem
import prunerr.operations


@mock.patch.dict(os.environ, prunerrtests.PrunerrTestCase.ENV)
class PrunerrDownloadItemTests(prunerrtests.PrunerrTestCase):
    """
    The Prunerr life-cycle stage operations tests.
    """

    def test_operations_reprs(self):
        """
        The Prunerr operation prints useful debugging details.
        """
        self.mock_responses()
        self.runner.update()
        download_client = list(self.runner.download_clients.values())[0]
        stage = prunerr.operations.PrunerrStage(
            "queued",
            self.config["stages"]["queued"],
            download_client,
        )
        self.assertIn(
            "name='queued'",
            repr(stage),
            "Life-cycle stage missing useful detail",
        )

        self.config["stages"]["queued"]["archives"]["name"] = "archives"
        operation = prunerr.operations.PrunerrOperation(
            stage,
            self.config["stages"]["queued"]["archives"],
        )
        self.assertIn(
            "name='archives'",
            repr(operation),
            "Life-cycle stage operation missing useful detail",
        )
