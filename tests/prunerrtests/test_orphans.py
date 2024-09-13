# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Prunerr removes files without download items according to configured rules.
"""

import os
import pathlib
import shutil

from unittest import mock

import prunerrtests

import prunerr
from prunerr import operations

HOME = pathlib.Path(__file__).parent / "home" / "free-space"
ENV = dict(prunerrtests.PrunerrTestCase.ENV, HOME=str(HOME))


@mock.patch.dict(os.environ, prunerrtests.PrunerrTestCase.ENV)
class PrunerrOrphansTests(prunerrtests.PrunerrTestCase):
    """
    Prunerr removes files without download items according to configured rules.
    """

    HOME = HOME
    CONFIG = HOME / ".config" / "prunerr.yml"
    ENV = ENV

    RESPONSES_DIR = prunerrtests.PrunerrTestCase.RESPONSES_DIR.parent / "orphans"

    def test_orphans(self):
        """
        Prunerr deletes orphaned files to orphans.
        """
        shutil.copy2(
            self.EXAMPLE_VIDEO,
            self.servarr_seeding_dir / self.EXAMPLE_VIDEO.name,
        )
        orphans_request_mocks = self.mock_responses()
        runner = prunerr.runner.PrunerrRunner(self.CONFIG)
        runner.update()
        orphans_results = runner.apply_(stages=["orphans"])
        self.assert_request_mocks(orphans_request_mocks)
        self.assertIn(
            operations.STAGE_ORPHANS,
            orphans_results,
            "Stage missing from orphan results",
        )
        self.assertIn(
            "prune",
            orphans_results[operations.STAGE_ORPHANS],
            "Operation missing from orphan results",
        )
        self.assertEqual(
            len(orphans_results[operations.STAGE_ORPHANS]["prune"]),
            1,
            "orphans orphan results wrong number of items",
        )
