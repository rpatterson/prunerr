# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Prunerr verifies corrupt items and deletes unregistered items.
"""

import os

from unittest import mock

import prunerrtests

import prunerr


@mock.patch.dict(os.environ, prunerrtests.PrunerrTestCase.ENV)
class PrunerrStageAllTests(prunerrtests.PrunerrTestCase):
    """
    Prunerr verifies corrupt items and deletes unregistered items.
    """

    RESPONSES_DIR = prunerrtests.PrunerrTestCase.RESPONSES_DIR.parent / "stage-all"

    def test_stage_all_workflow(self):
        """
        Prunerr verifies corrupt items and deletes unregistered items.
        """
        stage_all_request_mocks = self.mock_responses()
        prunerr.apply_(self.runner, stages=["all"])
        self.assert_request_mocks(stage_all_request_mocks)

    def test_stage_all_apply(self):
        """
        Apply the ``all:`` stage operations as a part of the ``apply`` sub-command.
        """
        stage_all_request_mocks = self.mock_responses()
        prunerr.apply_(self.runner, stages=["all"])
        self.assert_request_mocks(stage_all_request_mocks)
