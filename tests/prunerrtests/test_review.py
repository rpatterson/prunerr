# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Prunerr performs various configurable action on download items accorging to rules.
"""

import os
import functools
import pathlib
import datetime
import logging

from unittest import mock

import prunerrtests

import prunerr


@mock.patch.dict(os.environ, prunerrtests.PrunerrTestCase.ENV)
class PrunerrReviewTests(prunerrtests.PrunerrTestCase):
    """
    Prunerr performs various configurable action on download items accorging to rules.
    """

    RESPONSES_DIR = (
        prunerrtests.PrunerrTestCase.RESPONSES_DIR.parent / "review-downloading"
    )
    DOWNLOAD_ITEM_INDEX = -1

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
                                prunerrtests.mock_get_torrent_response,
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
        prunerr.review(self.runner)
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
                                prunerrtests.mock_get_torrent_response,
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
        prunerr.review(self.runner)
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
                                prunerrtests.mock_get_torrent_response,
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
        # Add the logging filter that excludes subsequent log messages for the same
        # item:
        item_logger = logging.getLogger(prunerr.downloaditem.__name__)
        self.addCleanup(item_logger.removeFilter, prunerr.utils.daemon_once_filter)
        item_logger.addFilter(prunerr.utils.daemon_once_filter)

        runner = prunerr.runner.PrunerrRunner(
            config=pathlib.Path(__file__).parent
            / "home"
            / "review-edge-cases"
            / ".config"
            / "prunerr.yml",
        )

        # On the first run, the per-item messages are logged and the item hash IDs
        # recorded:
        self.mock_responses(
            self.RESPONSES_DIR.parent / "review-edge-cases",
        )
        runner.update()
        runner.review()

        # Now on the next run, those log messages for those same items are not repeated:
        runner.quiet = True
        for download_client_url in self.download_client_urls:
            self.set_up_download_item_files(download_client_url)
        self.set_up_download_item(
            self.download_client_items_responses[self.DOWNLOAD_CLIENT_URL]["arguments"][
                "torrents"
            ][self.DOWNLOAD_ITEM_INDEX]["name"]
        )
        self.mock_responses(
            self.RESPONSES_DIR.parent / "review-edge-cases",
        )
        # Simulate a change in the configuration so that the reviews will be repeated:
        runner.config_file.touch()
        if hasattr(self, "assertNoLogs"):
            with self.assertNoLogs(  # pragma: no cover
                prunerr.downloaditem.logger,
                level=logging.WARNING,
            ):
                runner.update()
                runner.review()
        else:
            # BBB: Python <3.10 compat
            with self.assertRaises(AssertionError):  # pragma: no cover
                with self.assertLogs(
                    prunerr.downloaditem.logger,
                    level=logging.WARNING,
                ):
                    runner.update()
                    runner.review()
