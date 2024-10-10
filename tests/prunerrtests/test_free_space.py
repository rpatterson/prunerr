# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Prunerr removes imported items to free space according to configured rules.
"""

import os
import pathlib
import shutil
import logging

from unittest import mock

import prunerrtests

import prunerr

HOME = pathlib.Path(__file__).parent / "home" / "free-space"
ENV = dict(prunerrtests.PrunerrTestCase.ENV, HOME=str(HOME))


@mock.patch.dict(os.environ, prunerrtests.PrunerrTestCase.ENV)
class PrunerrFreeSpaceTests(prunerrtests.PrunerrTestCase):
    """
    Prunerr removes imported items to free space according to configured rules.
    """

    HOME = HOME
    CONFIG = HOME / ".config" / "prunerr.yml"
    ENV = ENV

    RESPONSES_DIR = (
        prunerrtests.PrunerrTestCase.RESPONSES_DIR.parent
        / "free-space-imported-sufficient"
    )

    def test_free_space_workflow(self):  # pylint: disable=too-many-statements
        """
        Prunerr removes imported items to free space according to configured rules.
        """
        # 0. Verify initial assumptions and conditions
        # Import a download item file into the library:
        self.mock_servarr_import_item(self.seeding_item)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Download item in incomplete path before any `free-space` runs",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Download item in downloading path before any `free-space` runs",
        )
        self.assertTrue(
            self.seeding_item.is_dir(),
            "Download item seeding path not directory before any `free-space` runs",
        )
        self.assertTrue(
            self.seeding_item_file.is_file(),
            "Download item file is not a file before any `free-space` runs",
        )
        self.assertEqual(
            self.seeding_item_file.stat().st_nlink,
            2,
            "Download item file not imported by Servarr",
        )

        # 1. There's still enough free space and no download items can be deleted.
        #    Running the `free-space` sub-command makes no no changes.
        imported_sufficient_request_mocks = self.mock_responses()
        imported_sufficient_before_session = imported_sufficient_request_mocks[
            "http://transmission:secret@localhost:9091/transmission/rpc"
        ]["POST"][1]["00-session-get"]["json"]["arguments"]
        self.assertGreater(
            imported_sufficient_before_session["download-dir-free-space"],
            self.min_free_space,
            "Not enough free space before 'imported sufficient' `free-space` run",
        )
        prunerr.apply_(self.runner, stages=["free-space"])
        self.assert_request_mocks(imported_sufficient_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Item in incomplete dir after 'imported sufficient' `free-space` run",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Item in downloading dir after 'imported sufficient' `free-space` run",
        )
        self.assertTrue(
            self.seeding_item.is_dir(),
            "Seeding item not dir after 'imported sufficient' `free-space` run",
        )
        self.assertTrue(
            self.seeding_item_file.is_file(),
            "Item file missing after 'imported sufficient' `free-space` run",
        )
        self.assertEqual(
            self.seeding_item_file.stat().st_nlink,
            2,
            "Download item file not imported by Servarr",
        )

        # 2. There's *not* enough free space and no download items can be
        #    deleted. Running the `free-space` sub-command still makes no changes.
        imported_insufficient_request_mocks = self.mock_responses(
            self.RESPONSES_DIR.parent / "free-space-imported-insufficient",
        )
        imported_insufficient_before_session = imported_insufficient_request_mocks[
            "http://transmission:secret@localhost:9091/transmission/rpc"
        ]["POST"][1]["00-session-get"]["json"]["arguments"]
        self.assertLess(
            imported_insufficient_before_session["download-dir-free-space"],
            self.min_free_space,
            "Too much free space before 'imported insufficient' `free-space` run",
        )
        imported_seeding_item = self.seeding_item.with_name(
            self.seeding_item_file.name.replace("S01E01", "S01E02").replace(
                "Corge",
                "Grault",
            ),
        )
        shutil.copy2(self.EXAMPLE_VIDEO, imported_seeding_item)
        seeding_import = self.manual_import.parent.with_name(imported_seeding_item.name)
        seeding_import.hardlink_to(imported_seeding_item)
        prunerr.apply_(self.runner, stages=["free-space"])
        self.assert_request_mocks(imported_insufficient_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Item in incomplete dir after 'imported insufficient' `free-space` run",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Item in downloading dir after 'imported insufficient' `free-space` run",
        )
        self.assertTrue(
            self.seeding_item.is_dir(),
            "Seeding item not dir after 'imported insufficient' `free-space` run",
        )
        self.assertTrue(
            self.seeding_item_file.is_file(),
            "Item file missing after 'imported insufficient' `free-space` run",
        )
        self.assertEqual(
            self.seeding_item_file.stat().st_nlink,
            2,
            "Download item file not imported by Servarr",
        )

        # 3. There's still not enough free space but now a download item can be
        #    deleted. There's still not enough free space after deleting it.
        self.imported_item_file.unlink()
        upgraded_insufficient_request_mocks = self.mock_responses(
            self.RESPONSES_DIR.parent / "free-space-upgraded-insufficient",
        )
        upgraded_insufficient_before_session = upgraded_insufficient_request_mocks[
            "http://transmission:secret@localhost:9091/transmission/rpc"
        ]["POST"][1]["00-session-get"]["json"]["arguments"]
        self.assertLess(
            upgraded_insufficient_before_session["download-dir-free-space"],
            self.min_free_space,
            "Too much free space before 'upgraded insufficient' `free-space` run",
        )
        second_seeding_file = self.seeding_item_file.with_name(self.manual_import.name)
        second_seeding_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.EXAMPLE_VIDEO, second_seeding_file)
        self.manual_import.parent.mkdir(parents=True, exist_ok=True)
        self.manual_import.hardlink_to(second_seeding_file)
        prunerr.apply_(self.runner, stages=["free-space"])
        self.assert_request_mocks(upgraded_insufficient_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Item in incomplete dir after 'upgraded insufficient' `free-space` run",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Item in downloading dir after 'upgraded insufficient' `free-space` run",
        )
        self.assertTrue(
            self.seeding_item.exists(),
            "Partially imported deleted in 'upgraded insufficient' `free-space` run",
        )

        # 4. There's still not enough free space but now enough download items can be
        #    deleted to free sufficient space.  Running the `free-space` sub-command
        #    deletes enough download items and their files to free sufficient space and
        #    resumed downloading.
        self.manual_import.unlink()
        upgraded_break_request_mocks = self.mock_responses(
            self.RESPONSES_DIR.parent / "free-space-upgraded-break",
        )
        upgraded_break_before_session = upgraded_break_request_mocks[
            "http://transmission:secret@localhost:9091/transmission/rpc"
        ]["POST"][1]["00-session-get"]["json"]["arguments"]
        self.assertLess(
            upgraded_break_before_session["download-dir-free-space"],
            self.min_free_space,
            "Too much free space before 'upgraded break' `free-space` run",
        )
        prunerr.apply_(self.runner, stages=["free-space"])
        self.assert_request_mocks(upgraded_break_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Item in incomplete dir after 'upgraded break' `free-space` run",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Item in downloading dir after 'upgraded break' `free-space` run",
        )
        self.assertFalse(
            self.seeding_item.exists(),
            "Seeding item still exists after 'upgraded break' `free-space` run",
        )

    def test_free_space_apply(self):
        """
        Prunerr deletes items to free space as a part of the `apply` sub-command.
        """
        self.mock_responses(
            self.RESPONSES_DIR.parent / "free-space-apply",
        )
        runner = prunerr.runner.PrunerrRunner(self.CONFIG)
        runner.update()
        apply_results = runner.apply_(stages=["free-space"])
        self.assertIn(
            prunerr.operations.STAGE_FREE_SPACE,
            apply_results,
            "Free Space results missing from `apply` sub-command results",
        )
        self.assertIn(
            prunerr.utils.normalize_url(self.download_client_urls[0]),
            apply_results[prunerr.operations.STAGE_FREE_SPACE],
            "Download client free space results missing from `apply` results",
        )
        self.assertIn(
            "prune",
            apply_results[prunerr.operations.STAGE_FREE_SPACE][
                prunerr.utils.normalize_url(self.download_client_urls[0])
            ],
            "Download client free space results missing operation results",
        )
        self.assertIsInstance(
            apply_results[prunerr.operations.STAGE_FREE_SPACE][
                prunerr.utils.normalize_url(self.download_client_urls[0])
            ]["prune"],
            dict,
            "Download client free space results operation results wrong type",
        )
        self.assertIsInstance(
            apply_results[prunerr.operations.STAGE_FREE_SPACE][
                prunerr.utils.normalize_url(self.download_client_urls[0])
            ]["prune"],
            dict,
            "Download client free space results wrong type from `apply` results",
        )
        self.assertEqual(
            len(
                apply_results[prunerr.operations.STAGE_FREE_SPACE][
                    prunerr.utils.normalize_url(self.download_client_urls[0])
                ]["prune"]
            ),
            1,
            "Download client free space results wrong number of items",
        )

    def test_free_remaining_downloads(self):
        """
        Prunerr logs how much space is required for remaining downloads.
        """
        remaining_downloads_request_mocks = self.mock_responses(
            self.RESPONSES_DIR.parent / "free-space-remaining",
        )
        with self.assertLogs(
            prunerr.downloadclient.logger,
            level=logging.DEBUG,
        ) as logged_msgs:
            prunerr.apply_(self.runner, stages=["free-space"])
        self.assert_request_mocks(remaining_downloads_request_mocks)
        self.assertIn(
            "greater than the available free",
            logged_msgs.records[-2].message,
            "Wrong logged record message",
        )
