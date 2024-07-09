# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Link imported files back into download items and verify, Servarr import inverse.
"""

import os
import shutil
import pathlib

from unittest import mock

import prunerrtests

import prunerr


@mock.patch.dict(os.environ, prunerrtests.PrunerrTestCase.ENV)
class PrunerrExportTests(prunerrtests.PrunerrTestCase):
    """
    Link imported files back into download items and verify, Servarr import inverse.
    """

    RESPONSES_DIR = prunerrtests.PrunerrTestCase.RESPONSES_DIR.parent / "export"

    def set_up_imported_files(self):
        """
        Simulate previous imports from download items.
        """
        # Normal Servarr import:
        self.imported_item_file.parent.mkdir(parents=True, exist_ok=True)
        self.imported_item_file.hardlink_to(self.downloaded_item_file)
        # Remove the item from the download client:
        # Removal from the download client is covered by the response fixtures.
        self.downloaded_item_file.unlink()

        # An import whose download item has been removed from the client:
        removed_download = self.imported_item_file.with_name(
            self.imported_item_file.name.replace("S01E01", "S01E02").replace(
                "Corge",
                "Grault",
            )
        )
        shutil.copy2(self.EXAMPLE_VIDEO, removed_download)
        # A different file, not a hard link to the imported file, is also still in place
        # in the download items old location:
        removed_download_parent = self.seeding_item_file.parent.with_name(
            removed_download.stem,
        )
        removed_download_parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            self.EXAMPLE_VIDEO,
            removed_download_parent / removed_download.name,
        )

        # A manual import of a 2nd file from a download item that was grabbed by Servarr
        # for just the 1st item:
        manual_import = self.imported_item_file.with_name(
            self.imported_item_file.name.replace(
                "S01E01",
                "S01E03",
            ).replace("Corge", "Garply"),
        )
        shutil.copy2(self.EXAMPLE_VIDEO, manual_import)
        # Also use this file as a download item file that is left after removal from the
        # download client and is used as the best data path to change the download
        # item's location too:
        self.seeding_item_file.parent.mkdir(parents=True, exist_ok=True)
        self.seeding_item_file.with_name(manual_import.name).hardlink_to(
            manual_import,
        )

        # An import download item all of whose download data files have been removed:
        missing_location = self.imported_item_file.with_name(
            self.imported_item_file.name.replace(
                "S01E01",
                "S01E04",
            ).replace("Corge", "Waldo"),
        )
        manual_dir = self.seeding_dir.with_name("manual")
        manual_len = len(manual_dir.parts)
        missing_item = (
            pathlib.Path(
                manual_dir,
                *self.seeding_item.parent.parts[manual_len:],
            )
            / missing_location.stem
        )
        (missing_item / missing_location.name).rename(missing_location)
        missing_item.rmdir()

        # An imported download item that is fully intact and requires no export actions:
        intact_download = self.imported_item_file.with_name(
            self.imported_item_file.name.replace("S01E01", "S01E05").replace(
                "Corge",
                "Xyzzy",
            )
        )
        intact_download.hardlink_to(
            self.seeding_item_file.with_name(intact_download.name),
        )

        # A manual import from a download item that is the only one in the download
        # client with its root name:
        manual_import_single_item = self.imported_item_file.with_name(
            self.imported_item_file.name.replace(
                "S01E01",
                "S01E08",
            ).replace("Corge", "Quux"),
        )
        shutil.copy2(self.EXAMPLE_VIDEO, manual_import_single_item)

    def test_export_workflow(self):
        """
        Link imported files back into download items and verify, Servarr import inverse.
        """
        # 1. Simulate previous imports from download items:
        self.set_up_imported_files()

        # 2. Run the `export` sub-command:
        export_request_mocks = self.mock_responses()
        runner = prunerr.runner.PrunerrRunner(self.CONFIG)
        runner.update()
        export_results = runner.export()
        self.assert_request_mocks(export_request_mocks)
        self.assertIn(
            self.servarr_urls[0],
            export_results,
            "Export results missing download client results",
        )
        self.assertIsInstance(
            export_results[self.servarr_urls[0]],
            dict,
            "Export results wrong download client results type",
        )
        self.assertEqual(
            len(export_results[self.servarr_urls[0]]),
            1,
            "Export results wrong number of download client results",
        )
        self.assertIn(
            "transmission",
            export_results[self.servarr_urls[0]],
            "Export results missing download client results",
        )
        self.assertIsInstance(
            export_results[self.servarr_urls[0]]["transmission"],
            dict,
            "Export results wrong download client results type",
        )
        self.assertEqual(
            len(export_results[self.servarr_urls[0]]["transmission"]),
            3,
            "Export results wrong number of download client results",
        )
        download_item_hash = "1FAFED76F4264B14934C13D7A306F94FEA4B3184"
        self.assertIn(
            download_item_hash,
            export_results[self.servarr_urls[0]]["transmission"],
            "Download client results missing download item",
        )
        self.assertIsInstance(
            export_results[self.servarr_urls[0]]["transmission"][download_item_hash],
            list,
            "Download item results wrong type",
        )
        self.assertEqual(
            len(
                export_results[self.servarr_urls[0]]["transmission"][download_item_hash]
            ),
            1,
            "Download item wrong number of results",
        )
        self.assertIn(
            str(self.imported_item_file),
            export_results[self.servarr_urls[0]]["transmission"][download_item_hash],
            "Download item results missing linked file",
        )

        # 3. The item has been added back to the download client, verified and resumed:
        self.assertTrue(
            self.seeding_item_file.exists(),
            "Export Seeding item file missing",
        )
        self.assertEqual(
            self.seeding_item_file.stat().st_nlink,
            2,
            "Export Seeding item file not a hard link",
        )
        self.assertTrue(
            self.seeding_item_file.samefile(self.imported_item_file),
            "Export Seeding item file not linked to imported file",
        )
        # Verifying and resuming the download item in the download client is covered by
        # the response fixtures.

    def test_export_main(self):
        """
        Test export execution as a CLI sub-command.
        """
        # Simulate previous imports from download items:
        self.set_up_imported_files()

        self.mock_responses()
        prunerr.main(
            args=[
                f"--config={self.CONFIG}",
                "export",
                "--extra-data-path",
                str(self.storage_dir / "archived"),
            ],
        )

    def test_export_empty(self):
        """
        Test export execution when there's nothing to do.
        """
        default_request_mocks = self.mock_responses(
            self.RESPONSES_DIR.with_name("export-empty"),
        )
        runner = prunerr.runner.PrunerrRunner(self.CONFIG)
        runner.update()
        export_results = runner.export()
        self.assert_request_mocks(default_request_mocks)
        self.assertIsNone(
            export_results,
            "Export without anything to do returned results",
        )
