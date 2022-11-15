"""
Test Prunerr syncing Servarr status to download item location.
"""

import os
import json
import unittest

from unittest import mock

import prunerr.servarr

from .. import tests


@mock.patch.dict(os.environ, tests.PrunerrTestCase.ENV)
class PrunerrSyncTests(tests.PrunerrTestCase):
    """
    Test Prunerr syncing Servarr status to download item location.
    """

    RESPONSES_DIR = tests.PrunerrTestCase.RESPONSES_DIR.parent / "sync-ungrabbed"

    def test_sync_usual_lifecycle(
        self,
    ):  # pylint: disable=too-many-statements,too-many-locals
        """
        Download items are moved to `seeding` when imported by Servarr.
        """
        # 0. Verify initial assumptions and conditions
        self.assertTrue(
            self.incomplete_item.is_dir(),
            "Download item is not a directory while downloading",
        )
        self.assertTrue(
            self.incomplete_item_file.is_file(),
            "Download item file is not a file while downloading",
        )
        self.assertEqual(
            self.incomplete_item_file.stat().st_nlink,
            1,
            "Download item file has more than one link before importing",
        )
        self.assertFalse(
            self.incomplete_item_data.exists(),
            "Prunerr data file exists prior to running",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Download item exists in downloaded path before finished downloading",
        )
        self.assertFalse(
            self.downloaded_item_data.exists(),
            "Prunerr data file exists in downloaded path before finished downloading",
        )
        self.assertFalse(
            self.seeding_item.exists(),
            "Download item exists in seeding path before finished downloading",
        )
        self.assertFalse(
            self.seeding_item_data.exists(),
            "Prunerr data file exists in seeding path before finished downloading",
        )

        # 1. Download item is grabbed by Servarr and added to the client but the history
        #    isn't visible in the Servarr API yet.  Running the `sync` sub-command
        #    results in no changes.
        ungrabbed_request_mocks = self.mock_responses()
        prunerr.main(args=[f"--config={self.CONFIG}", "sync"])
        self.assert_request_mocks(ungrabbed_request_mocks)
        self.assertTrue(
            self.incomplete_item.is_dir(),
            "Download item is not a directory while downloading",
        )
        self.assertTrue(
            self.incomplete_item_file.is_file(),
            "Download item file is not a file while downloading",
        )
        self.assertEqual(
            self.incomplete_item_file.stat().st_nlink,
            1,
            "Download item file has more than one link before importing",
        )
        self.assertTrue(
            self.incomplete_item_data.is_file(),
            "Prunerr data file isn't a file after first sync",
        )
        with self.incomplete_item_data.open() as incomplete_data_opened:
            grabbed_prunerr_data = json.load(incomplete_data_opened)
        self.assertNotIn(
            "dirId",
            grabbed_prunerr_data,
            "Servarr DB id in Prunerr data before finding Servarr history",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Download item exists in downloaded path before finished downloading",
        )
        self.assertFalse(
            self.downloaded_item_data.exists(),
            "Prunerr data file exists in downloaded path before finished downloading",
        )
        self.assertFalse(
            self.seeding_item.exists(),
            "Download item exists in seeding path before finished downloading",
        )
        self.assertFalse(
            self.seeding_item_data.exists(),
            "Prunerr data file exists in seeding path before finished downloading",
        )

        # 2. The grabbed event becomes visible in the Servarr API and Prunerr records
        #    enough to match the item to the correct `dirId`, IOW `seriesId` or
        #    `movieId` so that further history lookups are much more efficient.
        grabbed_request_mocks = self.mock_responses(
            tests.PrunerrTestCase.RESPONSES_DIR.parent / "sync-grabbed",
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "sync"])
        self.assert_request_mocks(grabbed_request_mocks)
        self.assertTrue(
            self.incomplete_item.is_dir(),
            "Download item is not a directory while downloading",
        )
        self.assertTrue(
            self.incomplete_item_file.is_file(),
            "Download item file is not a file while downloading",
        )
        self.assertEqual(
            self.incomplete_item_file.stat().st_nlink,
            1,
            "Download item file has more than one link before importing",
        )
        self.assertTrue(
            self.incomplete_item_data.is_file(),
            "Prunerr data file isn't a file after finding Servarr history",
        )
        with self.incomplete_item_data.open() as incomplete_data_opened:
            grabbed_prunerr_data = json.load(incomplete_data_opened)
        self.assertIn(
            "dirId",
            grabbed_prunerr_data,
            "Prunerr data Servarr DB id not found after finding Servarr history",
        )
        self.assertEqual(
            grabbed_prunerr_data["dirId"],
            1,
            "Wrong Prunerr data Servarr DB id after finding Servarr history",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Download item exists in downloaded path before finished downloading",
        )
        self.assertFalse(
            self.downloaded_item_data.exists(),
            "Prunerr data file exists in downloaded path before finished downloading",
        )
        self.assertFalse(
            self.seeding_item.exists(),
            "Download item exists in seeding path before finished downloading",
        )
        self.assertFalse(
            self.seeding_item_data.exists(),
            "Prunerr data file exists in seeding path before finished downloading",
        )

        # 3. The download client finishes downloading the item and moves it into the
        #    Servarr downloads directory.  Running the `sync` sub-command moves the
        #    Prunerr data file along with the item.
        self.mock_download_client_complete_item()
        # Ensure the test fixture is correct that the download item has finished
        # downloading in the download client.
        completed_responses_dir = (
            tests.PrunerrTestCase.RESPONSES_DIR.parent / "sync-completed"
        )
        download_items_response_path = (
            completed_responses_dir
            / "http"
            / "transmission%3Asecret%40localhost%3A9091"
            / "transmission"
            / "rpc"
            / "POST"
            / "01-torrent-get"
            / "response.json"
        )
        with download_items_response_path.open() as download_items_response_opened:
            download_items_response = json.load(download_items_response_opened)
        imported_download_item = [
            download_item
            for download_item in download_items_response["arguments"]["torrents"]
            if download_item["name"] == self.download_item_title
        ][0]
        self.assertIsNotNone(
            imported_download_item,
            "Could not find downloaded item in request mock",
        )
        self.assertEqual(
            imported_download_item["leftUntilDone"],
            0,
            "Downloaded item not finished downloading in request mock",
        )
        self.assertEqual(
            imported_download_item["percentDone"],
            1,
            "Downloaded item not finished downloading in request mock",
        )
        # Proceed with the `sync` sub-command
        completed_request_mocks = self.mock_responses(completed_responses_dir)
        prunerr.main(args=[f"--config={self.CONFIG}", "sync"])
        self.assert_request_mocks(completed_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Download item incomplete path exists after finished downloading",
        )
        self.assertFalse(
            self.incomplete_item_data.exists(),
            "Prunerr data file in incomplete path after finished downloading",
        )
        self.assertTrue(
            self.downloaded_item.is_dir(),
            "Download item not in downloaded path after finished downloading",
        )
        self.assertTrue(
            self.downloaded_item_file.is_file(),
            "Download item file is not a file after finished downloading",
        )
        self.assertEqual(
            self.downloaded_item_file.stat().st_nlink,
            1,
            "Download item file has more than one link before importing",
        )
        self.assertTrue(
            self.downloaded_item_data.is_file(),
            "Prunerr data file not in downloaded path after finished downloading",
        )
        with self.downloaded_item_data.open() as downloaded_data_opened:
            completed_prunerr_data = json.load(downloaded_data_opened)
        self.assertIn(
            "dirId",
            completed_prunerr_data,
            "Prunerr data Servarr DB id not found after finding Servarr history",
        )
        self.assertEqual(
            completed_prunerr_data["dirId"],
            1,
            "Wrong Prunerr data Servarr DB id after finding Servarr history",
        )
        self.assertFalse(
            self.seeding_item.exists(),
            "Download item exists in seeding path after finished downloading",
        )
        self.assertFalse(
            self.seeding_item_data.exists(),
            "Prunerr data file exists in seeding path after finished downloading",
        )

        # 4. Servarr imports at least some of the item's files but the history isn't
        #    visible in the Servarr API yet.  Running the `sync` sub-command results in
        #    no changes.
        self.mock_servarr_import_item()
        completed_request_mocks = self.mock_responses(
            tests.PrunerrTestCase.RESPONSES_DIR.parent / "sync-completed",
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "sync"])
        self.assert_request_mocks(completed_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Download item incomplete path exists after finished downloading",
        )
        self.assertFalse(
            self.incomplete_item_data.exists(),
            "Prunerr data file in incomplete path after finished downloading",
        )
        self.assertTrue(
            self.downloaded_item.is_dir(),
            "Download item not in downloaded path after finished downloading",
        )
        self.assertTrue(
            self.downloaded_item_file.is_file(),
            "Download item file is not a file after finished downloading",
        )
        self.assertEqual(
            self.downloaded_item_file.stat().st_nlink,
            2,
            "Download item file wrong number of links after import",
        )
        self.assertTrue(
            self.downloaded_item_data.is_file(),
            "Prunerr data file not in downloaded path after finished downloading",
        )
        with self.downloaded_item_data.open() as downloaded_data_opened:
            completed_prunerr_data = json.load(downloaded_data_opened)
        self.assertIn(
            "dirId",
            completed_prunerr_data,
            "Prunerr data Servarr DB id not found after finding Servarr history",
        )
        self.assertEqual(
            completed_prunerr_data["dirId"],
            1,
            "Wrong Prunerr data Servarr DB id after finding Servarr history",
        )
        self.assertFalse(
            self.seeding_item.exists(),
            "Download item exists in seeding path after finished downloading",
        )
        self.assertFalse(
            self.seeding_item_data.exists(),
            "Prunerr data file exists in seeding path after finished downloading",
        )

        # 5. The import event becomes visible in the Servarr API history.  The item is
        #    moved from `downloads` to `seeding` and the Prunerr data file along with
        #    it.
        # TODO: Redundant download item update download client request
        import_request_mocks = self.mock_responses(
            tests.PrunerrTestCase.RESPONSES_DIR.parent / "sync-import",
            # Insert a dynamic response mock to handle moving imported download items
            {
                "http://transmission:secret@localhost:9091/transmission/rpc": {
                    "POST": {
                        "03-torrent-set-location": dict(
                            json=self.mock_move_torrent_response,
                        ),
                    },
                },
            },
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "sync"])
        self.assert_request_mocks(import_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Download item in incomplete path after import",
        )
        self.assertFalse(
            self.incomplete_item_data.exists(),
            "Prunerr data file in incomplete path after import",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Download item in downloading path after import",
        )
        self.assertFalse(
            self.downloaded_item_data.exists(),
            "Prunerr data file in downloading path after import",
        )
        self.assertTrue(
            self.seeding_item.is_dir(),
            "Download item seeding path is not a directory after import",
        )
        self.assertTrue(
            self.seeding_item_file.is_file(),
            "Download item file is not a file after import",
        )
        self.assertEqual(
            self.seeding_item_file.stat().st_nlink,
            2,
            "Download item file wrong number of links after import",
        )
        self.assertTrue(
            self.seeding_item_data.is_file(),
            "Prunerr data file isn't a file after being imported",
        )
        with self.seeding_item_data.open() as import_data_opened:
            import_prunerr_data = json.load(import_data_opened)
        self.assertIn(
            "dirId",
            import_prunerr_data,
            "Prunerr data Servarr DB id not found after import",
        )
        self.assertEqual(
            import_prunerr_data["dirId"],
            1,
            "Wrong Prunerr data Servarr DB id after import",
        )

        # 6. Servarr upgrades the item file and deletes it but the history isn't
        #    visible in the Servarr API yet.  Running the `sync` sub-command results in
        #    no changes.
        self.mock_servarr_delete_file()
        imported_request_mocks = self.mock_responses(
            tests.PrunerrTestCase.RESPONSES_DIR.parent / "sync-imported",
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "sync"])
        self.assert_request_mocks(imported_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Download item in incomplete path after deleted",
        )
        self.assertFalse(
            self.incomplete_item_data.exists(),
            "Prunerr data file in incomplete path after deleted",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Download item in downloading path after deleted",
        )
        self.assertFalse(
            self.downloaded_item_data.exists(),
            "Prunerr data file in downloading path after deleted",
        )
        self.assertTrue(
            self.seeding_item.is_dir(),
            "Download item seeding path is not a directory after deleted",
        )
        self.assertTrue(
            self.seeding_item_file.is_file(),
            "Download item file is not a file after deleted",
        )
        self.assertEqual(
            self.seeding_item_file.stat().st_nlink,
            1,
            "Download item file has too many links after deleted",
        )
        self.assertTrue(
            self.seeding_item_data.is_file(),
            "Prunerr data file isn't a file after being deleted",
        )
        with self.seeding_item_data.open() as imported_data_opened:
            imported_prunerr_data = json.load(imported_data_opened)
        self.assertIn(
            "dirId",
            imported_prunerr_data,
            "Prunerr data Servarr DB id not found after deleted",
        )
        self.assertEqual(
            imported_prunerr_data["dirId"],
            1,
            "Wrong Prunerr data Servarr DB id after deleted",
        )

        # 7. The delete event becomes visible in the Servarr API history.  Running the
        #    `sync` sub-command results in no changes.
        deleted_request_mocks = self.mock_responses(
            tests.PrunerrTestCase.RESPONSES_DIR.parent / "sync-deleted",
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "sync"])
        self.assert_request_mocks(deleted_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Download item in incomplete path after deleted",
        )
        self.assertFalse(
            self.incomplete_item_data.exists(),
            "Prunerr data file in incomplete path after deleted",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Download item in downloading path after deleted",
        )
        self.assertFalse(
            self.downloaded_item_data.exists(),
            "Prunerr data file in downloading path after deleted",
        )
        self.assertTrue(
            self.seeding_item.is_dir(),
            "Download item seeding path is not a directory after deleted",
        )
        self.assertTrue(
            self.seeding_item_file.is_file(),
            "Download item file is not a file after deleted",
        )
        self.assertEqual(
            self.seeding_item_file.stat().st_nlink,
            1,
            "Download item file has too many links after deleted",
        )
        self.assertTrue(
            self.seeding_item_data.is_file(),
            "Prunerr data file isn't a file after being deleted",
        )
        with self.seeding_item_data.open() as imported_data_opened:
            imported_prunerr_data = json.load(imported_data_opened)
        self.assertIn(
            "dirId",
            imported_prunerr_data,
            "Prunerr data Servarr DB id not found after deleted",
        )
        self.assertEqual(
            imported_prunerr_data["dirId"],
            1,
            "Wrong Prunerr data Servarr DB id after deleted",
        )

    @unittest.skip("TODO")
    def test_sync_imported_before(self):
        """
        Items imported before Prunerr has seen a grabbed event are still synced.
        """
        raise NotImplementedError("TODO")

    @unittest.skip("TODO")
    def test_sync_user_deleted(self):
        """
        Items not automatically imported and deleted by they user are synced correctly.

        For example, if the item is of lower quality than the currently imported item
        and the user decides to delete it from the Servarr queue instead.  That item
        should still be moved to `seeding`.
        """
        raise NotImplementedError("TODO")

    @unittest.skip("TODO")
    def test_sync_orphaned_data_files(self):
        """
        Gather orphaned Prunerr data files as items are moved outside of Prunerr.

        When the `sync` sub-command is run, check all Prunerr-managed paths for Prunerr
        data files corresponding to the download item, choose the newest one, move it
        into place and backup the rest with logging warnings for unexpected locations
        and backups.
        """
        raise NotImplementedError("TODO")
