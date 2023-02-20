"""
Test moving download items that Servarr has acted on.
"""

import os
import functools
import pathlib
import json

from unittest import mock

import prunerr.servarr

from .. import tests


@mock.patch.dict(os.environ, tests.PrunerrTestCase.ENV)
class PrunerrMoveTests(tests.PrunerrTestCase):
    """
    Test moving download items that Servarr has acted on.
    """

    RESPONSES_DIR = tests.PrunerrTestCase.RESPONSES_DIR.parent / "move-ungrabbed"

    def test_move_usual_lifecycle(
        self,
    ):  # pylint: disable=too-many-statements
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
            self.downloaded_item.exists(),
            "Download item exists in downloaded path before finished downloading",
        )
        self.assertFalse(
            self.seeding_item.exists(),
            "Download item exists in seeding path before finished downloading",
        )

        # 1. Download item is grabbed by Servarr and added to the client but the history
        #    isn't visible in the Servarr API yet.  Running the `move` sub-command
        #    results in no changes.
        ungrabbed_request_mocks = self.mock_responses()
        prunerr.main(args=[f"--config={self.CONFIG}", "move"])
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
        self.assertFalse(
            self.downloaded_item.exists(),
            "Download item exists in downloaded path before finished downloading",
        )
        self.assertFalse(
            self.seeding_item.exists(),
            "Download item exists in seeding path before finished downloading",
        )

        # 2. The grabbed event becomes visible in the Servarr API and Prunerr records
        #    enough to match the item to the correct `dirId`, IOW `seriesId` or
        #    `movieId` so that further history lookups are much more efficient.
        grabbed_request_mocks = self.mock_responses(
            tests.PrunerrTestCase.RESPONSES_DIR.parent / "move-grabbed",
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "move"])
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
        self.assertFalse(
            self.downloaded_item.exists(),
            "Download item exists in downloaded path before finished downloading",
        )
        self.assertFalse(
            self.seeding_item.exists(),
            "Download item exists in seeding path before finished downloading",
        )

        # 3. The download client finishes downloading the item and moves it into the
        #    Servarr downloads directory.  Running the `move` sub-command makes no
        #    changes.
        self.mock_download_client_complete_item()
        # Ensure the test fixture is correct that the download item has finished
        # downloading in the download client.
        completed_responses_dir = (
            tests.PrunerrTestCase.RESPONSES_DIR.parent / "move-completed"
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
        # Proceed with the `move` sub-command
        completed_request_mocks = self.mock_responses(completed_responses_dir)
        prunerr.main(args=[f"--config={self.CONFIG}", "move"])
        self.assert_request_mocks(completed_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Download item incomplete path exists after finished downloading",
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
        self.assertFalse(
            self.seeding_item.exists(),
            "Download item exists in seeding path after finished downloading",
        )

        # 4. Servarr imports at least some of the item's files but the history isn't
        #    visible in the Servarr API yet.  Running the `move` sub-command results in
        #    no changes.
        self.mock_servarr_import_item()
        completed_request_mocks = self.mock_responses(
            tests.PrunerrTestCase.RESPONSES_DIR.parent / "move-completed",
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "move"])
        self.assert_request_mocks(completed_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Download item incomplete path exists after finished downloading",
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
        self.assertFalse(
            self.seeding_item.exists(),
            "Download item exists in seeding path after finished downloading",
        )

        # 5. The import event becomes visible in the Servarr API history.  The item is
        #    moved from `downloads` to `seeding`.
        import_request_mocks = self.mock_responses(
            tests.PrunerrTestCase.RESPONSES_DIR.parent / "move-import",
            # Insert a dynamic response mock to handle moving imported download items
            {
                "http://transmission:secret@localhost:9091/transmission/rpc": {
                    "POST": {
                        "02-torrent-set-location": {
                            "json": functools.partial(
                                self.mock_move_torrent_response,
                                delay=1,
                            ),
                        },
                    },
                },
            },
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "move"])
        self.assert_request_mocks(import_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Download item in incomplete path after import",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Download item in downloading path after import",
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

        # 6. Servarr upgrades the item file and deletes it but the history isn't
        #    visible in the Servarr API yet.  Running the `move` sub-command results in
        #    no changes.
        self.mock_servarr_delete_file()
        imported_request_mocks = self.mock_responses(
            tests.PrunerrTestCase.RESPONSES_DIR.parent / "move-imported",
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "move"])
        self.assert_request_mocks(imported_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Download item in incomplete path after deleted",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Download item in downloading path after deleted",
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

        # 7. The delete event becomes visible in the Servarr API history.  Running the
        #    `move` sub-command results in no changes.
        deleted_request_mocks = self.mock_responses(
            tests.PrunerrTestCase.RESPONSES_DIR.parent / "move-deleted",
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "move"])
        self.assert_request_mocks(deleted_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Download item in incomplete path after deleted",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Download item in downloading path after deleted",
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

    def test_move_imported_before(self):
        """
        Items imported before Prunerr has seen a grabbed event are still moved.

        This also describes items "grabbed" by the user outside of Servarr and then
        manually imported into Servarr.  Such items still have an imported event with
        the download item hash id, so they can still be moved without issue.
        """
        self.mock_download_client_complete_item()
        self.mock_servarr_import_item()
        imported_before_request_mocks = self.mock_responses(
            tests.PrunerrTestCase.RESPONSES_DIR.parent / "move-imported-before",
            # Insert a dynamic response mock to handle moving imported download items
            {
                "http://transmission:secret@localhost:9091/transmission/rpc": {
                    "POST": {
                        "02-torrent-set-location": {
                            "json": self.mock_move_torrent_response,
                        },
                    },
                },
            },
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "move"])
        self.assert_request_mocks(imported_before_request_mocks)
        self.assertFalse(
            self.incomplete_item.exists(),
            "Download item in incomplete path after import",
        )
        self.assertFalse(
            self.downloaded_item.exists(),
            "Download item in downloading path after import",
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

    def test_move_exec(self):
        """
        Prunerr moves imported items as a part of the `exec` sub-command.
        """
        self.mock_download_client_complete_item()
        self.mock_servarr_import_item()
        runner = prunerr.runner.PrunerrRunner(
            pathlib.Path(__file__).parent
            / "home"
            / "move-exec"
            / ".config"
            / "prunerr.yml",
        )
        self.mock_responses(
            tests.PrunerrTestCase.RESPONSES_DIR.parent / "move-import",
            # Insert a dynamic response mock to handle moving imported download items
            {
                "http://transmission:secret@localhost:9091/transmission/rpc": {
                    "POST": {
                        "02-torrent-set-location": {
                            "json": self.mock_move_torrent_response,
                        },
                    },
                },
            },
        )
        runner.update()
        exec_results = runner.exec_()
        self.assertIn(
            "move",
            exec_results,
            "Move results missing from `exec` sub-command results",
        )
        self.assertIn(
            self.servarr_urls[0],
            exec_results["move"],
            "Servarr move results missing from `exec` sub-command results",
        )
        self.assertIn(
            self.download_client_urls[0],
            exec_results["move"][self.servarr_urls[0]],
            "Download client move results missing from `exec` sub-command results",
        )
        self.assertIsInstance(
            exec_results["move"][self.servarr_urls[0]][self.download_client_urls[0]],
            list,
            "Download client move results wrong type from `exec` sub-command results",
        )
        self.assertEqual(
            len(
                exec_results["move"][self.servarr_urls[0]][self.download_client_urls[0]]
            ),
            1,
            "Download client move results wrong number of items",
        )

    def test_move_timeout(self):
        """
        Prunerr times out moving imported items.
        """
        self.mock_download_client_complete_item()
        self.mock_servarr_import_item()
        runner = prunerr.runner.PrunerrRunner(config=self.CONFIG)
        self.mock_responses(
            tests.PrunerrTestCase.RESPONSES_DIR.parent / "move-import",
            # Insert a dynamic response mock to handle moving imported download items
            {
                "http://transmission:secret@localhost:9091/transmission/rpc": {
                    "POST": {
                        "02-torrent-set-location": {
                            "json": functools.partial(
                                self.mock_move_torrent_response,
                                delay=1,
                            ),
                        },
                    },
                },
            },
        )
        runner.update()
        servarr = list(runner.servarrs.values())[0]
        with self.assertRaises(
            prunerr.downloadclient.DownloadClientTimeout,
            msg="Long download item move did not time out",
        ):
            list(servarr.download_clients.values())[0].move(move_timeout=0)
