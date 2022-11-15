"""
Prunerr performs various configurable action on download items accorging to rules.
"""

import os
import functools
import datetime

from unittest import mock

import prunerr.downloadclient

from .. import tests


@mock.patch.dict(os.environ, tests.PrunerrTestCase.ENV)
class PrunerrReviewTests(tests.PrunerrTestCase):
    """
    Prunerr performs various configurable action on download items accorging to rules.
    """

    RESPONSES_DIR = tests.PrunerrTestCase.RESPONSES_DIR.parent / "review-downloading"

    def test_review_bandwidth_priority(self):
        """
        A review configuration raises the bandwidth priority of private indexer items.
        """
        # 0. Verify initial assumptions and conditions.  The download client has two
        #    torrents, one from a private indexer and one from a public indexer.
        downloading_request_mocks = self.mock_responses(
            self.RESPONSES_DIR,
            # Insert a dynamic response mock to add recent dates
            {
                "http://transmission:secret@localhost:9091/transmission/rpc": {
                    "POST": {
                        "01-torrent-get": dict(
                            json=functools.partial(
                                self.mock_get_torrent_response,
                                [
                                    {},
                                    {
                                        "addedDate": (
                                            datetime.datetime.now()
                                            - datetime.timedelta(days=1)
                                        ).timestamp()
                                    },
                                ],
                            ),
                        ),
                    },
                },
            },
        )
        downloading_before_torrents = downloading_request_mocks[
            "http://transmission:secret@localhost:9091/transmission/rpc"
        ]["POST"][1]["01-torrent-get"]["from_mock_dir"]["json"]["arguments"]["torrents"]
        self.assertEqual(
            [torrent["isPrivate"] for torrent in downloading_before_torrents],
            [False, True],
            "Wrong number of download torrents or wrong private vs public indexers",
        )
        self.assertEqual(
            [torrent["bandwidthPriority"] for torrent in downloading_before_torrents],
            [0, 0],
            "Wrong number of torrents or wrong priorities",
        )
        public_indexer_before_torrent, _ = downloading_before_torrents
        private_indexer_item = self.incomplete_item
        private_indexer_item_file = self.incomplete_item_file
        private_indexer_item_data = self.incomplete_item_data
        public_indexer_item = private_indexer_item.with_name(
            public_indexer_before_torrent["name"],
        )
        public_indexer_item_file = (
            public_indexer_item.parent
            / public_indexer_before_torrent["files"][0]["name"]
        )
        public_indexer_item_data = public_indexer_item.with_name(
            "{public_indexer_item}{downloadclient.DATA_FILE_SUFFIX}",
        )
        self.assertTrue(
            private_indexer_item.is_dir(),
            "Private indexer item is not a directory while downloading",
        )
        self.assertTrue(
            private_indexer_item_file.is_file(),
            "Private indexer item file is not a file while downloading",
        )
        self.assertEqual(
            private_indexer_item_file.stat().st_nlink,
            1,
            "Private indexer item file has more than one link before importing",
        )
        self.assertFalse(
            private_indexer_item_data.exists(),
            "Prunerr data file exists prior to running sub-command",
        )
        self.assertTrue(
            public_indexer_item.is_dir(),
            "Public indexer item is not a directory while downloading",
        )
        self.assertTrue(
            public_indexer_item_file.is_file(),
            "Public indexer item file is not a file while downloading",
        )
        self.assertEqual(
            public_indexer_item_file.stat().st_nlink,
            1,
            "Public indexer item file has more than one link before importing",
        )
        self.assertFalse(
            public_indexer_item_data.exists(),
            "Prunerr data file exists prior to running sub-command",
        )
        self.assertFalse(
            self.servarr_downloaded_dir.exists(),
            "The downloaded items directory exists before downloading is complete",
        )
        self.assertFalse(
            self.servarr_seeding_dir.exists(),
            "The seeding items directory exists before Servarr import",
        )

        # 1. Run the `review` sub-command.  The private item's bandwidth priority is
        # increased and the stalled public item is both deleted from the download client
        # and the release is blacklisted in Servarr.  Nothing else is changed.
        prunerr.main(args=[f"--config={self.CONFIG}", "review"])
        self.assert_request_mocks(downloading_request_mocks)
        (private_indexer_reviewed_torrent,) = downloading_request_mocks[
            "http://transmission:secret@localhost:9091/transmission/rpc"
        ]["POST"][1]["05-torrent-get"]["json"]["arguments"]["torrents"]
        self.assertEqual(
            private_indexer_reviewed_torrent["isPrivate"],
            True,
            "Private indexer download item missing the private torrent flag",
        )
        self.assertEqual(
            private_indexer_reviewed_torrent["bandwidthPriority"],
            1,
            "Private indexer download item wrong bandwidth priority",
        )
        self.assertTrue(
            private_indexer_item.is_dir(),
            "Private indexer item is not a directory while downloading",
        )
        self.assertTrue(
            private_indexer_item_file.is_file(),
            "Private indexer item file is not a file while downloading",
        )
        self.assertEqual(
            private_indexer_item_file.stat().st_nlink,
            1,
            "Private indexer item file has more than one link before importing",
        )
        self.assertTrue(
            private_indexer_item_data.exists(),
            "Prunerr data file not created by sub-command",
        )
        self.assertFalse(
            public_indexer_item.exists(),
            "Public indexer item not deleted by review",
        )
        self.assertFalse(
            public_indexer_item_data.exists(),
            "Prunerr data file not deleted by review",
        )
        self.assertFalse(
            self.servarr_downloaded_dir.exists(),
            "The downloaded items directory exists before downloading is complete",
        )
        self.assertFalse(
            self.servarr_seeding_dir.exists(),
            "The seeding items directory exists before Servarr import",
        )
