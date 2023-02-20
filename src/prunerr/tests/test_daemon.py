"""
Tests covering the Prunerr `daemon` sub-command.
"""

import os
import pathlib
import time
import socket

from unittest import mock

import prunerr.downloadclient

from .. import tests

HOME = pathlib.Path(__file__).parent / "home" / "daemon"
ENV = dict(tests.PrunerrTestCase.ENV, HOME=str(HOME))


class PrunerrDaemonTestException(BaseException):
    """
    Special exception used to break the daemon loop.
    """


@mock.patch.dict(os.environ, ENV)
class PrunerrDaemonTests(tests.PrunerrTestCase):
    """
    Tests covering the Prunerr `daemon` sub-command.
    """

    HOME = HOME
    CONFIG = HOME / ".config" / "prunerr.yml"
    ENV = ENV

    RESPONSES_DIR = tests.PrunerrTestCase.RESPONSES_DIR.parent / "daemon"

    def mock_poll_delay_response(
        self,
        request=None,
        context=None,
        response_mock=None,
    ):  # pylint: disable=unused-argument
        """
        Sleep for more than the daemon loop poll time before sending response.
        """
        time.sleep(1)
        return response_mock["from_mock_dir"]["json"]

    def mock_network_retry_response(
        self,
        request=None,
        context=None,
        response_mock=None,
    ):
        """
        Raise an exception while running `exec` that `daemon` catches.
        """
        raise socket.error("Temporary network connection error")

    def mock_exit_daemon_response(
        self,
        request=None,
        context=None,
        response_mock=None,
    ):
        """
        Simulate an exception to exit the `daemon` sub-command.
        """
        raise PrunerrDaemonTestException("Exit the daemon loop")

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
                        "01-torrent-get": {"json": self.mock_poll_delay_response},
                    },
                },
                "http://localhost:8989/api/v3/queue/1?apikey=&blacklist=true": {
                    "DELETE": {
                        "0-response": {"json": self.mock_network_retry_response},
                    },
                },
                "http://localhost:8989/api/v3/system/status?apikey=": {
                    "GET": {
                        "2-response": {"json": self.mock_exit_daemon_response},
                    },
                },
            },
        )
        with self.assertRaises(
            PrunerrDaemonTestException,
            msg="Daemon loop exited with wrong exception",
        ):
            prunerr.main(args=[f"--config={self.CONFIG}", "daemon"])
        self.assert_request_mocks(daemon_request_mocks)
