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

    RESPONSES_DIR = prunerrtests.PrunerrTestCase.RESPONSES_DIR.parent / "re-add"

    def test_re_add_workflow(self):
        """
        Remove and re-add all download items with nothing downloaded.
        """
        torrent_path = (
            self.tmp_path
            / "config"
            / "torrents"
            / "1fafed76f4264b14934c13d7a306f94fea4b3184.torrent"
        )
        torrent_path.parent.mkdir(parents=True, exist_ok=True)
        torrent_path.write_text('["Example torrent for testing"]')
        self.mock_responses()
        prunerr.re_add(self.runner)
        # TODO: Add test coverage.
