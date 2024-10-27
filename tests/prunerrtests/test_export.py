# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Link imported files back into download items and verify, Servarr import inverse.
"""

import os
import pathlib
import shutil

from unittest import mock

import bencode
import requests
import requests_mock

import prunerrtests

import prunerr


@mock.patch.dict(os.environ, prunerrtests.PrunerrTestCase.ENV)
class PrunerrExportTests(prunerrtests.PrunerrTestCase):
    """
    Link imported files back into download items and verify, Servarr import inverse.
    """

    RESPONSES_DIR = prunerrtests.PrunerrTestCase.RESPONSES_DIR.parent / "export"

    torrents_dir: pathlib.Path
    resume_dir: pathlib.Path

    def set_up_imported_files(self) -> dict:
        """
        Simulate previous imports from download items.

        :return: The mock request fixtures.
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
        shutil.copy2(self.EXAMPLE_VIDEO, self.manual_import)
        # Also use this file as a download item file that is left after removal from the
        # download client and is used as the best data path to change the download
        # item's location too:
        self.seeding_item_file.parent.mkdir(parents=True, exist_ok=True)
        self.seeding_item_file.with_name(self.manual_import.name).hardlink_to(
            self.manual_import,
        )

        # An import download item all of whose download data files have been removed:
        missing_location = self.imported_item_file.with_name(
            self.imported_item_file.name.replace(
                "S01E01",
                "S01E04",
            ).replace("Corge", "Waldo"),
        )
        missing_item = self.downloaded_dir / missing_location.stem
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

        # A Radarr import of a movie:
        movie_seeding_file = (
            self.seeding_item_file.parents[4]
            / "Radarr"
            / "Videos"
            / "Movies"
            / "Bar.Movie.1980.WEB-DL.x265.HEVC-RELEASER"
            / "Bar.Movie.1980.WEB-DL.x265.HEVC-RELEASER.mkv"
        )
        movie_seeding_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.EXAMPLE_VIDEO, movie_seeding_file)
        movie_import = (
            self.imported_item_file.parents[3]
            / "Movies"
            / "Bar Movie (1980) [tmdbid-1]"
            / "Bar.Movie.1980.WEB-DL.x265.HEVC-RELEASER.mkv"
        )
        movie_import.parent.mkdir(parents=True, exist_ok=True)
        movie_import.hardlink_to(movie_seeding_file)

        self.torrents_dir = self.tmp_path / "config" / "torrents"
        self.resume_dir = self.torrents_dir.parent / "resume"
        download_hashes = [
            downlod_item_mock["hashString"]
            for downlod_item_mock in self.download_client_items_responses[
                self.DOWNLOAD_CLIENT_URL
            ]["arguments"]["torrents"]
        ]
        download_hashes.append("8b8060bf22c942b1b6cabb8e5b840e445b840e44")
        for download_hash in download_hashes:
            torrent_path = self.torrents_dir / f"{download_hash}.torrent"
            torrent_path.parent.mkdir(parents=True, exist_ok=True)
            torrent_path.write_bytes(bencode.bencode({}))
            resume_path = self.resume_dir / f"{torrent_path.stem}.resume"
            resume_path.parent.mkdir(parents=True, exist_ok=True)
            resume_path.write_bytes(
                bencode.bencode(
                    {
                        "added-date": 10,
                        "done-date": 10,
                    }
                )
            )

        return self.mock_responses(
            self.RESPONSES_DIR,
            {
                "http://transmission:secret@localhost:9091/transmission/rpc": {
                    "POST": {
                        # Also remove the mock Transmission `/config/resume/*.resume`
                        # files:
                        "05-torrent-remove": {
                            "json": self.mock_remove_torrent_response,
                        },
                        "09-torrent-remove": {
                            "json": self.mock_remove_torrent_response,
                        },
                        "14-torrent-remove": {
                            "json": self.mock_remove_torrent_response,
                        },
                        "18-torrent-remove": {
                            "json": self.mock_remove_torrent_response,
                        },
                    },
                },
            },
        )

    def mock_remove_torrent_response(
        self,
        request: requests.Request,  # pylint: disable=unused-argument
        context: requests_mock.response._Context,
        response_mock: dict,
    ) -> dict:
        """
        Simulate the download client removing a download item.

        :param request: The request to mock.
        :param context: The mock response context.
        :param response_mock: The fixture from the ``./responses/*/`` directory.
        :return: The response JSON from the fixture.
        """
        download_hash = response_mock["from_mock_dir"]["request"]["json"]["arguments"][
            "ids"
        ][0]
        (self.resume_dir / f"{download_hash}.resume").unlink()
        context.headers.update(response_mock.get("headers", {}))
        return response_mock["from_mock_dir"][prunerrtests.MIME_MINOR_JSON]

    def test_export_workflow(self):
        """
        Link imported files back into download items and verify, Servarr import inverse.
        """
        # 1. Simulate previous imports from download items and mock the requests:
        export_request_mocks = self.set_up_imported_files()

        # 2. Run the `export` sub-command:
        self.runner.update()
        export_results = self.runner.export()
        self.assert_request_mocks(export_request_mocks)
        self.assertIn(
            self.servarr_urls[0],
            export_results,
            "Export results missing download clients",
        )
        self.assertIsInstance(
            export_results[self.servarr_urls[0]],
            dict,
            "Export results wrong download client results type",
        )
        self.assertEqual(
            len(export_results[self.servarr_urls[0]]),
            1,
            "Export results wrong number of download clients",
        )
        self.assertIn(
            "Foo Series",
            export_results[self.servarr_urls[0]],
            "Export results missing series results",
        )
        self.assertIsInstance(
            export_results[self.servarr_urls[0]]["Foo Series"],
            list,
            "Export results wrong series results type",
        )
        self.assertEqual(
            len(export_results[self.servarr_urls[0]]["Foo Series"]),
            3,
            "Export results wrong number of hard linked files",
        )
        self.assertIn(
            str(self.seeding_item_file),
            export_results[self.servarr_urls[0]]["Foo Series"],
            "Export results missing hard linked file",
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
        prunerr.export(self.runner)

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
