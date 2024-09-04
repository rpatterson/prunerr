# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Tests covering the Prunerr `daemon` sub-command.
"""

import os
import typing
import pathlib
import time

from unittest import mock

import prunerrtests

import prunerr

HOME = pathlib.Path(__file__).parent / "home" / "daemon"
ENV = dict(prunerrtests.PrunerrTestCase.ENV, HOME=str(HOME))


class PrunerrDaemonTestException(BaseException):
    """
    Testing exception used to break the daemon loop.
    """


def mock_poll_delay_response(  # pylint: disable=missing-param-doc,missing-return-doc
    request: dict,  # pylint: disable=unused-argument
    context: dict,  # pylint: disable=unused-argument
    response_mock: dict,
) -> dict:
    """
    Sleep for more than the daemon loop poll time before sending response.
    """
    time.sleep(1)
    return response_mock["from_mock_dir"]["json"]


def mock_network_retry_response(  # pylint: disable=missing-param-doc,missing-raises-doc
    request: typing.Optional[dict] = None,
    context: typing.Optional[dict] = None,
    response_mock: typing.Optional[dict] = None,
):
    """
    Raise an exception while running `exec` that `daemon` catches.
    """
    raise ConnectionError("Temporary network connection error")


def mock_exit_daemon_response(  # pylint: disable=missing-param-doc,missing-raises-doc
    request: typing.Optional[dict] = None,
    context: typing.Optional[dict] = None,
    response_mock: typing.Optional[dict] = None,
):
    """
    Simulate an exception to exit the `daemon` sub-command.
    """
    raise PrunerrDaemonTestException("Exit the daemon loop")


@mock.patch.dict(os.environ, ENV)
@mock.patch(
    "prunerr.runner.PrunerrRunner.EXAMPLE_CONFIG",
    HOME / ".config" / "prunerr-example.yml",
)
class PrunerrDaemonTests(prunerrtests.PrunerrTestCase):
    """
    Tests covering the Prunerr `daemon` sub-command.
    """

    HOME = HOME
    CONFIG = HOME / ".config" / "prunerr.yml"
    ENV = ENV

    RESPONSES_DIR = prunerrtests.PrunerrTestCase.RESPONSES_DIR.parent / "daemon"

    def setUp(self):
        """
        Remove the ``ntfy`` logging handler after, regardless of success of failure.
        """
        super().setUp()
        self.addCleanup(prunerr.logger.removeHandler, prunerr.utils.notify_handler)

    def test_daemon_command(self):
        """
        The daemon sub-command loops twice and exits.
        """
        daemon_request_mocks = self.mock_responses(
            self.RESPONSES_DIR,
            # Insert a dynamic response mock to add recent dates
            {
                "http://transmission:secret@localhost:9091/transmission/rpc": {
                    "POST": {
                        "01-torrent-get": {"json": mock_poll_delay_response},
                    },
                },
                "http://localhost:8989/api/v3/queue/1?apikey=&blacklist=true": {
                    "DELETE": {
                        "0-response": {"json": mock_network_retry_response},
                    },
                },
                "http://localhost:8989/api/v3/system/status?apikey=": {
                    "GET": {
                        "2-response": {"json": mock_exit_daemon_response},
                    },
                },
            },
        )
        runner = prunerr.runner.PrunerrRunner(self.CONFIG)
        with self.assertRaises(
            PrunerrDaemonTestException,
            msg="Daemon loop exited with wrong exception",
        ):
            prunerr.daemon(runner)
        self.assert_request_mocks(daemon_request_mocks)
