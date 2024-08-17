# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Remove and re-add all download items with nothing downloaded.
"""

import os

from unittest import mock

import prunerrtests

import prunerr


@mock.patch.dict(os.environ, prunerrtests.PrunerrTestCase.ENV)
class PrunerrReAddTests(prunerrtests.PrunerrTestCase):
    """
    Remove and re-add all download items with nothing downloaded.
    """

    def test_re_add_workflow(self):
        """
        Remove and re-add all download items with nothing downloaded.
        """
        self.mock_responses()
        prunerr.main(args=[f"--config={self.CONFIG}", "re-add"])
        # TODO: Add test coverage.
