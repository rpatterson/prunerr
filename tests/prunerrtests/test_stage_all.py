# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Prunerr verifies corrupt items and deletes unregistered items.
"""

import os
import logging

from unittest import mock

import prunerrtests

import prunerr


@mock.patch.dict(os.environ, prunerrtests.PrunerrTestCase.ENV)
class PrunerrStageAllTests(prunerrtests.PrunerrTestCase):
    """
    Prunerr verifies corrupt items and deletes unregistered items.
    """

    RESPONSES_DIR = prunerrtests.PrunerrTestCase.RESPONSES_DIR.parent / "stage-all"

    def setUp(self):
        """
        Import the seeding download item file into the Servarr library.
        """
        super().setUp()
        unimport_imported_file = self.imported_item_file.with_name(
            self.imported_item_file.name.replace(
                "S01E01",
                "S01E04",
            ).replace("Corge", "Waldo"),
        )
        unimport_item = self.seeding_item.with_name(unimport_imported_file.stem)
        unimport_item_file = unimport_item / unimport_imported_file.name
        unimport_imported_file.parent.mkdir(parents=True, exist_ok=True)
        unimport_imported_file.hardlink_to(unimport_item_file)

    def test_stage_all_workflow(self):
        """
        Prunerr verifies corrupt items and deletes unregistered items.
        """
        stage_all_request_mocks = self.mock_responses()
        with self.assertLogs(
            prunerr.downloaditem.logger,
            level=logging.DEBUG,
        ) as logged_msgs:
            prunerr.apply_(self.runner, stages=["all"])
        self.assertIn(
            "Not in the Servarr queue",
            logged_msgs.records[1].message,
            "Wrong logged record message",
        )
        self.assert_request_mocks(stage_all_request_mocks)

    def test_stage_all_apply(self):
        """
        Apply the ``all:`` stage operations as a part of the ``apply`` sub-command.
        """
        stage_all_request_mocks = self.mock_responses()
        prunerr.apply_(self.runner, stages=["all"])
        self.assert_request_mocks(stage_all_request_mocks)
