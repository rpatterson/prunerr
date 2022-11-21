"""
Prunerr removes imported items to free space according to configured rules.
"""

import os
import shutil
import logging

from unittest import mock

import prunerr.downloadclient

from .. import tests


@mock.patch.dict(os.environ, tests.PrunerrTestCase.ENV)
class PrunerrFreeSpaceTests(tests.PrunerrTestCase):
    """
    Prunerr removes imported items to free space according to configured rules.
    """

    RESPONSES_DIR = (
        tests.PrunerrTestCase.RESPONSES_DIR.parent / "free-space-imported-sufficient"
    )

    def test_free_space_workflow(self):
        """
        Prunerr removes imported items to free space according to configured rules.
        """
        shutil.copy2(
            self.EXAMPLE_VIDEO,
            self.servarr_seeding_dir / self.EXAMPLE_VIDEO.name,
        )
        # 0. Verify initial assumptions and conditions
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
        self.assertFalse(
            imported_sufficient_before_session["speed-limit-down-enabled"],
            "Download limit enabled before 'imported sufficient' `free-space` run",
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "free-space"])
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
        #    deleted. Running the `free-space` sub-command stops the download client
        #    from downloading further.
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
        self.assertFalse(
            imported_insufficient_before_session["speed-limit-down-enabled"],
            "Download limit enabled before 'imported insufficient' `free-space` run",
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "free-space"])
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

        # 3. There's still not enough free space but now enough download items can be
        #    deleted to free sufficient space.  Running the `free-space` sub-command
        #    deletes enough download items and their files to free sufficient space and
        #    resumed downloading.
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
        self.assertTrue(
            upgraded_insufficient_before_session["speed-limit-down-enabled"],
            "Download limit disabled before 'upgraded insufficient' `free-space` run",
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "free-space"])
        self.assert_request_mocks(upgraded_insufficient_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Item in incomplete dir after 'upgraded insufficient' `free-space` run",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Item in downloading dir after 'upgraded insufficient' `free-space` run",
        )
        self.assertFalse(
            self.seeding_item.is_dir(),
            "Seeding item still exists after 'upgraded insufficient' `free-space` run",
        )

    def test_free_space_exec(self):
        """
        Prunerr deletes items to free space as a part of the `exec` sub-command.
        """
        self.mock_responses(
            self.RESPONSES_DIR.parent / "free-space-upgraded-insufficient",
        )
        runner = prunerr.runner.PrunerrRunner(self.CONFIG)
        runner.update()
        exec_results = runner.exec_()
        self.assertIn(
            "free-space",
            exec_results,
            "Free Space results missing from `exec` sub-command results",
        )
        self.assertIn(
            self.download_client_urls[0],
            exec_results["free-space"],
            "Download client free space results missing from `exec` results",
        )
        self.assertIsInstance(
            exec_results["free-space"][self.download_client_urls[0]],
            list,
            "Download client free space results wrong type from `exec` results",
        )
        self.assertEqual(
            len(exec_results["free-space"][self.download_client_urls[0]]),
            1,
            "Download client free space results wrong number of items",
        )

    def test_free_space_unregistered(self):
        """
        Prunerr deletes unregistered items to free space.
        """
        self.incomplete_dir.mkdir(parents=True, exist_ok=True)
        self.seeding_item.rename(self.incomplete_dir / self.seeding_item.name)
        unregistered_request_mocks = self.mock_responses(
            self.RESPONSES_DIR.parent / "free-space-unregistered",
        )
        runner = prunerr.runner.PrunerrRunner(self.CONFIG)
        runner.update()
        unregistered_results = runner.free_space()
        self.assert_request_mocks(unregistered_request_mocks)
        self.assertIn(
            self.download_client_urls[0],
            unregistered_results,
            "Download client free space results missing from unregistered item results",
        )
        self.assertIsInstance(
            unregistered_results[self.download_client_urls[0]],
            list,
            "Download client free space results wrong unregistered item results type",
        )
        self.assertEqual(
            len(unregistered_results[self.download_client_urls[0]]),
            1,
            "Free space unregistered item results wrong number of items",
        )

    def test_free_space_orphans(self):
        """
        Prunerr deletes orphaned files to free space.
        """
        shutil.copy2(
            self.EXAMPLE_VIDEO,
            self.servarr_seeding_dir / self.EXAMPLE_VIDEO.name,
        )
        orphans_request_mocks = self.mock_responses(
            self.RESPONSES_DIR.parent / "free-space-orphans",
        )
        runner = prunerr.runner.PrunerrRunner(self.CONFIG)
        runner.update()
        orphans_results = runner.free_space()
        self.assert_request_mocks(orphans_request_mocks)
        self.assertIn(
            self.download_client_urls[0],
            orphans_results,
            "Download client free space results missing from orphan results",
        )
        self.assertIsInstance(
            orphans_results[self.download_client_urls[0]],
            list,
            "Download client free space results wrong orphan results type",
        )
        self.assertEqual(
            len(orphans_results[self.download_client_urls[0]]),
            1,
            "Free space orphan results wrong number of items",
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
            prunerr.main(args=[f"--config={self.CONFIG}", "free-space"])
        self.assert_request_mocks(remaining_downloads_request_mocks)
        self.assertIn(
            "greater than the available free",
            logged_msgs.records[-2].message,
            "Wrong logged record message",
        )
