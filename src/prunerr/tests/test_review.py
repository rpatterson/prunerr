"""
Prunerr performs various configurable action on download items accorging to rules.
"""

import os
import functools
import pathlib
import datetime
import logging

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
                        "01-torrent-get": {
                            "json": functools.partial(
                                self.mock_get_torrent_response,
                                [
                                    {},
                                    {
                                        "addedDate": (
                                            datetime.datetime.now()
                                            - datetime.timedelta(days=1)
                                        ).timestamp()
                                    },
                                    {
                                        "addedDate": (
                                            datetime.datetime.now()
                                            - datetime.timedelta(days=1)
                                        ).timestamp()
                                    },
                                ],
                            ),
                        },
                    },
                },
            },
        )
        downloading_before_torrents = downloading_request_mocks[
            "http://transmission:secret@localhost:9091/transmission/rpc"
        ]["POST"][1]["01-torrent-get"]["from_mock_dir"]["json"]["arguments"]["torrents"]
        self.assertEqual(
            [torrent["isPrivate"] for torrent in downloading_before_torrents],
            [False, True, True],
            "Wrong number of download torrents or wrong private vs public indexers",
        )
        self.assertEqual(
            [torrent["bandwidthPriority"] for torrent in downloading_before_torrents],
            [0, 0, 0],
            "Wrong number of torrents or wrong priorities",
        )
        public_indexer_before_torrent, _, _ = downloading_before_torrents
        private_indexer_item = self.incomplete_item
        private_indexer_item_file = self.incomplete_item_file
        public_indexer_item = private_indexer_item.with_name(
            public_indexer_before_torrent["name"],
        )
        # Sometimes downloading items can be in the downloaded directory instead of the
        # incomplete directory when moved by the user or previously downloaded but
        # corrupt, then verified and resumed.
        self.servarr_downloaded_dir.mkdir(parents=True, exist_ok=True)
        public_indexer_item = public_indexer_item.rename(
            self.servarr_downloaded_dir / public_indexer_item.name,
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
            public_indexer_item.is_file(),
            "Public indexer item is not a file while downloading",
        )
        self.assertEqual(
            public_indexer_item.stat().st_nlink,
            1,
            "Public indexer item file has more than one link before importing",
        )
        self.assertTrue(
            self.servarr_downloaded_dir.is_dir(),
            "The downloaded items directory isn't a directory",
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
        self.assertFalse(
            public_indexer_item.exists(),
            "Public indexer item not deleted by review",
        )
        self.assertFalse(
            self.servarr_seeding_dir.exists(),
            "The seeding items directory exists before Servarr import",
        )

        # 2. Run the `review` sub-command again.  Since all changes have already been
        # made, no further changes are made.
        reviewed_request_mocks = self.mock_responses(
            self.RESPONSES_DIR.parent / "review-reviewed",
            # Insert a dynamic response mock to add recent dates
            {
                "http://transmission:secret@localhost:9091/transmission/rpc": {
                    "POST": {
                        "01-torrent-get": {
                            "json": functools.partial(
                                self.mock_get_torrent_response,
                                [
                                    {
                                        "addedDate": (
                                            datetime.datetime.now()
                                        ).timestamp()
                                    },
                                    {
                                        "addedDate": (
                                            datetime.datetime.now()
                                        ).timestamp()
                                    },
                                ],
                            ),
                        },
                    },
                },
            },
        )
        prunerr.main(args=[f"--config={self.CONFIG}", "review"])
        self.assert_request_mocks(reviewed_request_mocks)
        (private_indexer_reviewed_torrent, _) = reviewed_request_mocks[
            "http://transmission:secret@localhost:9091/transmission/rpc"
        ]["POST"][1]["01-torrent-get"]["from_mock_dir"]["json"]["arguments"]["torrents"]
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
        self.assertFalse(
            public_indexer_item.exists(),
            "Public indexer item not deleted by review",
        )
        self.assertFalse(
            self.servarr_seeding_dir.exists(),
            "The seeding items directory exists before Servarr import",
        )

    def test_review_edge_cases(self):
        """
        Review of a download item without a queue record logs a warning.

        Also covers deleting download item without a blacklisting it, a review
        without any configured change in the request mock assertions, and nonsensical
        item timestamps.
        """
        runner = prunerr.runner.PrunerrRunner(
            config=pathlib.Path(__file__).parent
            / "home"
            / "review-edge-cases"
            / ".config"
            / "prunerr.yml",
        )
        self.mock_responses(
            self.RESPONSES_DIR.parent / "review-edge-cases",
            # Insert a dynamic response mock to nonsensical dates
            {
                "http://transmission:secret@localhost:9091/transmission/rpc": {
                    "POST": {
                        "01-torrent-get": {
                            "json": functools.partial(
                                self.mock_get_torrent_response,
                                [
                                    {},
                                    {},
                                    {},
                                    {
                                        # Done date is before added date
                                        "addedDate": (
                                            datetime.datetime.now()
                                            - datetime.timedelta(days=1)
                                        ).timestamp(),
                                        "doneDate": (
                                            datetime.datetime.now()
                                            - datetime.timedelta(days=2)
                                        ).timestamp(),
                                    },
                                    {
                                        # Added date is in the future
                                        "addedDate": (
                                            datetime.datetime.now()
                                            + datetime.timedelta(days=1)
                                        ).timestamp(),
                                        "doneDate": 0,
                                    },
                                ],
                            ),
                        },
                    },
                },
            },
        )
        runner.update()
        with self.assertLogs(
            prunerr.downloaditem.logger,
            level=logging.WARNING,
        ) as logged_msgs:
            runner.review()
        self.assertIn(
            "not in any Servarr queue",
            logged_msgs.records[0].message,
            "Wrong logged record message",
        )

    def test_review_edge_cases_quiet(self):
        """
        Second Review of a download item without a queue record doesn't logs a warning.
        """
        runner = prunerr.runner.PrunerrRunner(
            config=pathlib.Path(__file__).parent
            / "home"
            / "review-edge-cases"
            / ".config"
            / "prunerr.yml",
        )
        runner.quiet = True
        self.mock_responses(
            self.RESPONSES_DIR.parent / "review-edge-cases",
        )
        runner.update()
        if hasattr(self, "assertNoLogs"):  # pragma: no cover
            with self.assertNoLogs(
                prunerr.downloaditem.logger,
                level=logging.WARNING,
            ):
                runner.review()
        else:  # pragma: no cover
            # BBB: Python <3.10 compat
            with self.assertRaises(AssertionError):
                with self.assertLogs(
                    prunerr.downloaditem.logger,
                    level=logging.WARNING,
                ):
                    runner.review()
