# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Prunerr performs various configurable action on download items accorging to rules.
"""

import os
import functools
import pathlib
import datetime
import shutil
import logging

from unittest import mock

import prunerrtests

import prunerr


@mock.patch.dict(os.environ, prunerrtests.PrunerrTestCase.ENV)
class PrunerrQueuedTests(prunerrtests.PrunerrTestCase):
    """
    Prunerr performs various configurable action on download items accorging to rules.
    """

    RESPONSES_DIR = (
        prunerrtests.PrunerrTestCase.RESPONSES_DIR.parent / "queued-downloading"
    )
    DOWNLOAD_ITEM_INDEX = -1

    def test_queued_bandwidth_priority(self):
        """
        A queued configuration raises the bandwidth priority of private indexer items.
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

        # 1. Run the `apply` sub-command.  The private item's bandwidth priority is
        # increased and the stalled public item is both deleted from the download client
        # and the release is blacklisted in Servarr.  Nothing else is changed.
        prunerr.apply_(self.runner, stages=["queued"])
        self.assert_request_mocks(downloading_request_mocks)
        (private_indexer_queued_torrent,) = downloading_request_mocks[
            "http://transmission:secret@localhost:9091/transmission/rpc"
        ]["POST"][1]["05-torrent-get"]["json"]["arguments"]["torrents"]
        self.assertEqual(
            private_indexer_queued_torrent["isPrivate"],
            True,
            "Private indexer download item missing the private torrent flag",
        )
        self.assertEqual(
            private_indexer_queued_torrent["bandwidthPriority"],
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
            "Public indexer item not deleted by queued operations",
        )
        self.assertFalse(
            self.servarr_seeding_dir.exists(),
            "The seeding items directory exists before Servarr import",
        )

        # 2. Run the `apply` sub-command again.  Since all changes have already been
        # made, no further changes are made.
        queued_request_mocks = self.mock_responses(
            self.RESPONSES_DIR.parent / "queued-applied",
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
        prunerr.apply_(self.runner, stages=["queued"])
        self.assert_request_mocks(queued_request_mocks)
        (private_indexer_queued_torrent, _) = queued_request_mocks[
            "http://transmission:secret@localhost:9091/transmission/rpc"
        ]["POST"][1]["01-torrent-get"]["from_mock_dir"]["json"]["arguments"]["torrents"]
        self.assertEqual(
            private_indexer_queued_torrent["isPrivate"],
            True,
            "Private indexer download item missing the private torrent flag",
        )
        self.assertEqual(
            private_indexer_queued_torrent["bandwidthPriority"],
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
            "Public indexer item not deleted by queued operation",
        )
        self.assertFalse(
            self.servarr_seeding_dir.exists(),
            "The seeding items directory exists before Servarr import",
        )

    def test_queued_edge_cases(self):
        """
        Queued operations for a download item without a queue record logs a warning.

        Also covers deleting download item without a blacklisting it, an operation
        without any configured change in the request mock assertions, and nonsensical
        item timestamps.
        """
        runner = prunerr.runner.PrunerrRunner(
            config=pathlib.Path(__file__).parent
            / "home"
            / "queued-edge-cases"
            / ".config"
            / "prunerr.yml",
        )
        self.mock_responses(
            self.RESPONSES_DIR.parent / "queued-edge-cases",
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
            runner.apply_(stages=["queued"])
        self.assertIn(
            "missing from Servarr queue",
            logged_msgs.records[-1].message,
            "Wrong logged record message",
        )

    def test_queued_edge_cases_quiet(self):
        """
        Second operations on a download item doesn't logs a warning.
        """
        # Add the logging filter that excludes subsequent log messages for the same
        # item:
        item_logger = logging.getLogger(prunerr.downloaditem.__name__)
        self.addCleanup(item_logger.removeFilter, prunerr.utils.daemon_once_filter)
        item_logger.addFilter(prunerr.utils.daemon_once_filter)

        runner = prunerr.runner.PrunerrRunner(
            config=pathlib.Path(__file__).parent
            / "home"
            / "queued-edge-cases"
            / ".config"
            / "prunerr.yml",
        )

        # On the first run, the per-item messages are logged and the item hash IDs
        # recorded:
        self.mock_responses(
            self.RESPONSES_DIR.parent / "queued-edge-cases",
        )
        runner.update()
        runner.apply_(stages=["queued"])

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
            self.RESPONSES_DIR.parent / "queued-edge-cases",
        )
        # Simulate a change in the configuration so that the operations will be
        # repeated:
        runner.config_file.touch()
        if hasattr(self, "assertNoLogs"):
            with self.assertNoLogs(  # pragma: no cover
                prunerr.downloaditem.logger,
                level=logging.WARNING,
            ):
                runner.update()
                runner.apply_(stages=["queued"])
        else:
            # BBB: Python <3.10 compat
            with self.assertRaises(AssertionError):  # pragma: no cover
                with self.assertLogs(
                    prunerr.downloaditem.logger,
                    level=logging.WARNING,
                ):
                    runner.update()
                    runner.apply_(stages=["queued"])


@mock.patch.dict(os.environ, prunerrtests.PrunerrTestCase.ENV)
class PrunerrReviewUpgradedTests(prunerrtests.PrunerrTestCase):
    """
    Prunerr also applies operations to releases to be upgraded identified in history.
    """

    RESPONSES_DIR = (
        prunerrtests.PrunerrTestCase.RESPONSES_DIR.parent / "review-upgraded"
    )

    def test_review_upgraded_releases(self):
        """
        Prunerr also reviews imported releases that queued releases will upgrade.
        """
        # Start with a seeding download item with 2 imported files:
        review_upgraded_request_mocks = self.mock_responses(
            self.RESPONSES_DIR.parent / "review-upgraded",
        )
        self.runner.update()
        releases = list(
            list(self.runner.servarrs.values())[0].download_clients.values(),
        )[0].releases
        imported_release = releases[0]
        self.imported_item_file.parent.mkdir(parents=True, exist_ok=True)
        self.imported_item_file.hardlink_to(self.seeding_item_file)
        second_seeding_item_file = imported_release.download_item.files[1].path
        shutil.copy2(self.EXAMPLE_VIDEO, second_seeding_item_file)
        second_imported_item_file = self.imported_item_file.with_name(
            second_seeding_item_file.name,
        )
        second_imported_item_file.hardlink_to(second_seeding_item_file)
        # And a queued release that will upgrade only one of the imported item's files:
        downloading_release = releases[1]

        # Verify initial conditions:
        self.assertEqual(
            imported_release.download_item.files[0].path.stat().st_nlink,
            2,
            "Imported release file wrong number of hard links",
        )
        self.assertEqual(
            second_seeding_item_file.stat().st_nlink,
            2,
            "Second imported release file wrong number of hard links",
        )
        self.assertTrue(
            imported_release.download_item.files[0].path.samefile(
                self.imported_item_file,
            ),
            "Imported release file not same file as imported file",
        )
        self.assertEqual(
            len(downloading_release.download_item.files),
            1,
            "Downloading release file wrong number of files",
        )
        self.assertEqual(
            downloading_release.download_item.files[0].path.stat().st_nlink,
            1,
            "Downloading release file wrong number of hard links",
        )

        # Run the `review` sub-command:
        with self.assertLogs(
            prunerr.downloaditem.logger,
            level=logging.ERROR,
        ) as logged_msgs:
            self.runner.apply_(stages=["upgraded"])
        self.assert_request_mocks(review_upgraded_request_mocks)

        # Verify that the review acted as expected:
        self.assertIn(
            "partially imported",
            logged_msgs.records[0].message.lower(),
            "Logged record message missing partially imported error",
        )

        download_item = list(self.runner.download_clients.values())[0].items[0]
        upgraded_file = download_item.release.upgraded_release.download_item.files[0]
        self.assertIn(
            "st_nlink=1",
            repr(upgraded_file.stat),
            "Simulated upgraded file stat missing patched field",
        )
        self.assertEqual(
            upgraded_file.stat.st_ino,
            download_item.files[0].stat.st_ino,
            "Simulated upgraded file stat wrong original field value",
        )
        download_item.release.clear()
