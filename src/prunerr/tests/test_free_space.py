"""
Prunerr removes imported items to free space according to configured rules.
"""

import os
import json

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
        imported_sufficient_before_session = json.loads(
            imported_sufficient_request_mocks[
                "http://transmission:secret@localhost:9091/transmission/rpc"
            ]["POST"][1][0]["content"],
        )["arguments"]
        self.assertGreater(
            imported_sufficient_before_session["download-dir-free-space"],
            self.min_download_free_space,
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
        imported_insufficient_before_session = json.loads(
            imported_insufficient_request_mocks[
                "http://transmission:secret@localhost:9091/transmission/rpc"
            ]["POST"][1][0]["content"],
        )["arguments"]
        self.assertLess(
            imported_insufficient_before_session["download-dir-free-space"],
            self.min_download_free_space,
            "Too much free space before 'imported insufficient' `free-space` run",
        )
        self.assertFalse(
            imported_insufficient_before_session["speed-limit-down-enabled"],
            "Download limit enabled before 'imported insufficient' `free-space` run",
        )
        import pdb; pdb.set_trace()
        prunerr.main(args=[f"--config={self.CONFIG}", "free-space"])
        imported_insufficient_after_session = json.loads(
            imported_insufficient_request_mocks[
                "http://transmission:secret@localhost:9091/transmission/rpc"
            ]["POST"][1][-1]["content"],
        )["arguments"]
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
        self.assertLess(
            imported_insufficient_after_session["download-dir-free-space"],
            self.min_download_free_space,
            "Too much free space after 'imported insufficient' `free-space` run",
        )
        self.assertTrue(
            imported_insufficient_after_session["speed-limit-down-enabled"],
            "Download limit disabled after 'imported insufficient' `free-space` run",
        )

        # 3. There's still not enough free space but now enough download items can be
        #    deleted to free sufficient space.  Running the `free-space` sub-command
        #    deletes enough download items and their files to free sufficient space and
        #    resumed downloading.
        upgraded_insufficient_request_mocks = self.mock_responses(
            self.RESPONSES_DIR.parent / "free-space-upgraded-insufficient",
        )
        upgraded_insufficient_before_session = json.loads(
            upgraded_insufficient_request_mocks[
                "http://transmission:secret@localhost:9091/transmission/rpc"
            ]["POST"][1][0]["content"],
        )["arguments"]
        self.assertLess(
            upgraded_insufficient_before_session["download-dir-free-space"],
            self.min_download_free_space,
            "Too much free space before 'upgraded insufficient' `free-space` run",
        )
        self.assertTrue(
            upgraded_insufficient_before_session["speed-limit-down-enabled"],
            "Download limit disabled before 'upgraded insufficient' `free-space` run",
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "free-space"])
        upgraded_insufficient_after_session = json.loads(
            upgraded_insufficient_request_mocks[
                "http://transmission:secret@localhost:9091/transmission/rpc"
            ]["POST"][1][-1]["content"],
        )["arguments"]
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
        self.assertGreater(
            upgraded_insufficient_after_session["download-dir-free-space"],
            self.min_download_free_space,
            "Not enough free space after 'upgraded insufficient' `free-space` run",
        )
        self.assertFalse(
            upgraded_insufficient_after_session["speed-limit-down-enabled"],
            "Download limit enabled after 'upgraded insufficient' `free-space` run",
        )
