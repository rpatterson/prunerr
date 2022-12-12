"""
Test Prunerr's interaction with download items.
"""

import os
import pathlib
import logging

from unittest import mock

import prunerr.runner

from .. import tests


@mock.patch.dict(os.environ, tests.PrunerrTestCase.ENV)
class PrunerrDownloadItemTests(tests.PrunerrTestCase):
    """
    Test the aggregation of download item configurations.
    """

    HOME = pathlib.Path(__file__).parent / "home" / "download-items"
    CONFIG = HOME / ".config" / "prunerr.yml"
    ENV = dict(tests.PrunerrTestCase.ENV, HOME=str(HOME))

    RESPONSES_DIR = tests.PrunerrTestCase.RESPONSES_DIR.parent / "download-items"

    def test_download_item_missing_files(self):
        """
        Download items default to the item's name for the root if it has no files.
        """
        runner = prunerr.runner.PrunerrRunner(config=self.CONFIG)
        self.mock_responses()
        runner.update()
        self.assertEqual(
            runner.download_clients[self.DOWNLOAD_CLIENT_URL].items[0].root_name,
            "Foo.Series.1970.S01E02.Grault.Episode.Title.WEB-DL.x265.HEVC-RELEASER",
            "Wrong root name for download item with no files",
        )

    def test_download_item_multiple_roots(self):
        """
        Download items log an error if the item has multiple root directories.
        """
        runner = prunerr.runner.PrunerrRunner(config=self.CONFIG)
        self.mock_responses()
        runner.update()
        with self.assertLogs(
            prunerr.downloaditem.logger,
            level=logging.ERROR,
        ) as logged_msgs:
            root_name = (
                runner.download_clients[self.DOWNLOAD_CLIENT_URL].items[1].root_name
            )
        self.assertEqual(
            len(logged_msgs.records),
            1,
            "Wrong number of download item logged records",
        )
        self.assertIn(
            "multiple roots",
            logged_msgs.records[0].message,
            "Wrong logged record message",
        )
        self.assertEqual(
            root_name,
            "Foo.Series.1970.S01E01.Corge.Episode.Title.WEB-DL.x265.HEVC-RELEASER",
            "Wrong root name for download item with no files",
        )

    def test_download_item_seconds_since_done(self):
        """
        Download items provide access to the time duration since finished downloading.
        """
        runner = prunerr.runner.PrunerrRunner(config=self.CONFIG)
        self.mock_responses()
        runner.update()
        download_items = runner.download_clients[self.DOWNLOAD_CLIENT_URL].items
        self.assertGreater(
            download_items[0].seconds_since_done,
            0,
            "Wrong download item time duration since finished downloading",
        )
        self.assertIsNone(
            download_items[1].seconds_since_done,
            "Downloading item has time duration since finished downloading",
        )
        self.assertGreater(
            download_items[2].seconds_since_done,
            0,
            "Wrong item start date time duration since finished downloading",
        )
        self.assertGreater(
            download_items[3].seconds_since_done,
            0,
            "Wrong item done date time duration since finished downloading",
        )

    def test_download_item_rate_total(self):
        """
        Download items provide access to the total download rate.
        """
        runner = prunerr.runner.PrunerrRunner(config=self.CONFIG)
        self.mock_responses()
        runner.update()
        download_items = runner.download_clients[self.DOWNLOAD_CLIENT_URL].items
        self.assertGreater(
            download_items[3].rate_total,
            0,
            "Wrong download item total download rate",
        )
