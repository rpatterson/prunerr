"""
Test Prunerr's configurable operations.
"""

import os
import logging

from unittest import mock

import prunerr.runner
import prunerr.downloadclient
import prunerr.downloaditem
import prunerr.operations

from .. import tests
from . import test_downloaditem


@mock.patch.dict(os.environ, tests.PrunerrTestCase.ENV)
class PrunerrDownloadItemTests(tests.PrunerrTestCase):
    """
    Test Prunerr's configurable operations.
    """

    HOME = test_downloaditem.PrunerrDownloadItemTests.HOME
    CONFIG = test_downloaditem.PrunerrDownloadItemTests.CONFIG
    RESPONSES_DIR = test_downloaditem.PrunerrDownloadItemTests.RESPONSES_DIR

    def setUp(self):  # pylint: disable=invalid-name
        """
        Assemble the components required to run operations.
        """
        super().setUp()

        runner = prunerr.runner.PrunerrRunner(config=self.CONFIG)
        runner.config = self.config
        self.download_client = prunerr.downloadclient.PrunerrDownloadClient(runner)
        self.operations = prunerr.operations.PrunerrOperations(self.download_client, {})

        # Collect a download client item
        self.mock_responses()
        self.download_client.update({"url": self.DOWNLOAD_CLIENT_URL})
        self.item = self.download_client.items[1]

    def test_operation_invalid_executor(self):
        """
        Executing an operation that doesn't exist raises a clear error.
        """
        with self.assertRaises(
            NotImplementedError,
            msg="Executing an operation that doesn't exist didn't raise an error",
        ):
            self.operations.exec_operations(
                [{"type": "foo"}],
                self.item,
            )

    def test_operation_invalid_options(self):
        """
        Some operation configuration options conflict.
        """
        with self.assertRaises(
            ValueError,
            msg="Executing invalid operation options didn't raise an error",
        ):
            self.operations.exec_operations(
                [
                    {
                        "type": "value",
                        "name": "status",
                        "equals": "seeding",
                        "maximum": 1,
                    },
                ],
                self.item,
            )

    def test_operation_invalid_reversed(self):
        """
        Some operation values can't be reversed.
        """
        with self.assertRaises(
            NotImplementedError,
            msg="Executing invalid operation reversal didn't raise an error",
        ):
            self.operations.exec_operations(
                [
                    {
                        "type": "value",
                        "name": "peersFrom",
                        "reversed": True,
                    },
                ],
                self.item,
            )

    def test_operation_invalid_value(self):
        """
        An operation for a non-existent attribute/property isn't included.
        """
        self.assertEqual(
            self.operations.exec_operations(
                [
                    {
                        "type": "value",
                        "name": "foo",
                    },
                ],
                self.item,
            )[1],
            (),
            "Wrong non-existent attribute/property result",
        )

    def test_operation_and(self):
        """
        The `and` operation executes multiple operations and requires all to be True.
        """
        include, sort_key = self.operations.exec_operations(
            [
                {
                    "type": "and",
                    "filter": True,
                    "operations": [
                        {
                            "type": "value",
                            "name": "status",
                            "equals": "seeding",
                        },
                        {
                            "type": "value",
                            "name": "priorities",
                        },
                    ],
                }
            ],
            self.item,
        )
        self.assertEqual(
            (include, sort_key),
            (False, (False,)),
            "Wrong `and` operation `False` result",
        )
        # If all operations return `True` the value of the last one is returned
        include, sort_key = self.operations.exec_operations(
            [
                {
                    "type": "and",
                    "filter": True,
                    "operations": [
                        {
                            "type": "value",
                            "name": "priorities",
                            "reversed": True,
                        },
                        {
                            "type": "value",
                            "name": "status",
                        },
                    ],
                }
            ],
            self.item,
        )
        self.assertEqual(
            (include, sort_key),
            (True, ("downloading",)),
            "Wrong `and` operation `True` result",
        )

    def test_operation_executor_files_count(self):
        """
        The files executor provides returns the count of item files.
        """
        self.assertEqual(
            self.operations.exec_operations(
                [
                    {
                        "type": "files",
                        "aggregation": "count",
                    },
                ],
                self.item,
            )[1][0],
            2,
            "Wrong item files count",
        )

    def test_operation_executor_files_sum(self):
        """
        The files executor provides returns the sum of item file sizes.
        """
        self.assertEqual(
            self.operations.exec_operations(
                [
                    {
                        "type": "files",
                        "aggregation": "sum",
                    },
                ],
                self.item,
            )[1][0],
            2147483648,
            "Wrong item files size sum",
        )

    def test_operation_executor_files_invalid_aggregation(self):
        """
        Executing invalid files aggregation exist raises a clear error.
        """
        with self.assertRaises(
            ValueError,
            msg="Executing invalid files aggregation doesn't raise a clear error.",
        ):
            self.operations.exec_operations(
                [
                    {
                        "type": "files",
                        "aggregation": "foo",
                    },
                ],
                self.item,
            )

    def test_operation_executor_files_missing(self):
        """
        The files executor tolerates missing/empty item files.
        """
        with self.assertLogs(
            prunerr.operations.logger,
            level=logging.DEBUG,
        ) as logged_msgs:
            self.assertIs(
                self.operations.exec_operations(
                    [
                        {
                            "type": "files",
                        },
                    ],
                    self.download_client.items[0],
                )[1][0],
                False,
                "Wrong missing item files result",
            )
            self.assertIs(
                self.operations.exec_operations(
                    [
                        {
                            "type": "files",
                        },
                    ],
                    self.download_client.items[0],
                )[1][0],
                False,
                "Wrong missing item files result",
            )
        self.assertEqual(
            len(logged_msgs.records),
            1,
            "Wrong number of operations logged records",
        )
        self.assertIn(
            "contains no files",
            logged_msgs.records[0].message,
            "Wrong logged record message",
        )
