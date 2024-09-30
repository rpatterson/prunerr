# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Test Prunerr's interaction with download clients.
"""
# Aggregate download client configurations from Servarr and the configuration file.

import os
import pathlib

from unittest import mock

import prunerrtests

import prunerr.runner
import prunerr.downloadclient
from prunerr import utils


@mock.patch.dict(os.environ, prunerrtests.PrunerrTestCase.ENV)
class PrunerrDownloadClientTests(prunerrtests.PrunerrTestCase):
    """
    Test the aggregation of download client configurations.
    """

    HOME = pathlib.Path(__file__).parent / "home" / "download-clients"
    CONFIG = HOME / ".config" / "prunerr.yml"
    ENV = dict(prunerrtests.PrunerrTestCase.ENV, HOME=str(HOME))

    RESPONSES_DIR = (
        prunerrtests.PrunerrTestCase.RESPONSES_DIR.parent / "download-clients"
    )

    SERVARR_DOWNLOAD_CLIENT_URLS = (
        # The usual case
        "http://transmission@localhost:9091/transmission/",
        # Simulate a Servarr instance with multiple download clients
        # Simulate a Servarr instance not using authentication
        "http://transmission@192.168.1.1:9091/transmission/",
    )
    # Simulate a download client not used by a Servarr instance
    # Simulate a download client using HTTPS/TLS/SSL
    INDEPENDENT_DOWNLOAD_CLIENT_URLS = ("https://transmission.example.com",)
    DOWNLOAD_CLIENT_URLS = (
        SERVARR_DOWNLOAD_CLIENT_URLS + INDEPENDENT_DOWNLOAD_CLIENT_URLS
    )

    def test_download_client_aggregation(self):
        """
        Download client configurations are aggregated from Servarr and the config file.
        """
        self.assertFalse(
            getattr(self.runner, "download_clients", None),
            "Download clients aggregated before `runner.update(...)`",
        )

        request_mocks = self.mock_responses()
        self.runner.update()
        for download_client in self.runner.download_clients.values():
            self.assertIsInstance(
                download_client.items,
                list,
                "Wrong download client items type",
            )
        self.assert_request_mocks(request_mocks)
        self.assertIn(
            "download_clients",
            dir(self.runner),
            "Download clients missing after `runner.update(...)`",
        )
        self.assertIsInstance(
            self.runner.download_clients,
            dict,
            "Wrong aggregated download clients type",
        )
        for download_client_url in self.DOWNLOAD_CLIENT_URLS:
            with self.subTest(download_client_url=download_client_url):
                self.assert_download_client(self.runner, download_client_url)

        # Ensure the same remote API/RPC client instances are used across download
        # client and servarr instance combinations to reduce requests and preserve any
        # caching the clients may do
        self.assertIs(
            self.runner.download_clients[self.SERVARR_DOWNLOAD_CLIENT_URLS[0]]
            .servarrs[self.servarr_downloaded_dir]
            .servarr.client,
            self.runner.download_clients[self.SERVARR_DOWNLOAD_CLIENT_URLS[1]]
            .servarrs[self.servarr_downloaded_dir]
            .servarr.client,
            "Servarr instance client not re-used across download clients",
        )
        self.assertIs(
            self.runner.servarrs[self.servarr_urls[0]]
            .download_clients[self.SERVARR_DOWNLOAD_CLIENT_URLS[0]]
            .download_client.client,
            self.runner.servarrs[self.servarr_urls[1]]
            .download_clients[self.SERVARR_DOWNLOAD_CLIENT_URLS[0]]
            .download_client.client,
            "Download client's RPC client not re-used across Servarr instances",
        )

    def assert_download_client(
        self,
        runner: prunerr.runner.PrunerrRunner,
        download_client_url: str,
    ):
        """
        Confirm that an individual download client is configured correctly.

        :param runner: The ``prunerr.runner.PrunerrRunner`` instance from which to get
            the download clients
        :param download_client_url: The URL of a test fixture download client
        """
        self.assertIn(
            download_client_url,
            runner.download_clients,
            "Aggregated download clients missing URL",
        )
        download_client = runner.download_clients[download_client_url]
        self.assertIn(
            "version",
            download_client.session,
            "Aggregated download client not connected",
        )
        self.assertIn(
            "config",
            dir(download_client),
            "Missing download client config missing",
        )
        if download_client_url not in self.SERVARR_DOWNLOAD_CLIENT_URLS:
            return

        # Download clients connected to Servarr instances
        self.assertIn(
            "servarrs",
            dir(download_client),
            "Download client missing Servarr clients",
        )
        self.assertIsInstance(
            download_client.servarrs,
            dict,
            "Download client wrong Servarr clients type",
        )
        for servarr_config in self.config["servarrs"].values():
            with self.subTest(servarr_url=servarr_config["url"]):
                servarr = runner.servarrs[servarr_config["url"]]
                if download_client_url not in servarr.download_clients:
                    continue
                servarr_download_client = servarr.download_clients[download_client_url]
                self.assertIn(
                    servarr_download_client.download_dir,
                    download_client.servarrs,
                    "Download client missing Servarr download directory",
                )
                self.assertIs(
                    download_client.servarrs[servarr_download_client.download_dir],
                    servarr_download_client,
                    "Wrong Servarr download client instance",
                )
                self.assertIn(
                    "config",
                    dir(servarr_download_client),
                    "Servarr download client missing config",
                )
                self.assertIsInstance(
                    servarr_download_client.config,
                    dict,
                    "Servarr download client wrong config type",
                )
                self.assertTrue(
                    servarr_download_client.config,
                    "Servarr download client empty config type",
                )
                self.assertIn(
                    "download_dir",
                    dir(servarr_download_client),
                    "Servarr download client missing download dir",
                )
                self.assertEqual(
                    servarr_download_client.download_dir,
                    self.tmp_path
                    / self.servarr_download_client_responses[servarr_config["url"]][0][
                        "fields"
                    ][7]["value"].lstrip(os.path.sep),
                    "Servarr download client wrong download dir",
                )

    def test_download_client_repr(self):
        """
        The download client representation provides useful information for debugging.
        """
        download_client = prunerr.downloadclient.PrunerrDownloadClient(self.runner)
        download_client.config = {"name": "Transmission"}
        self.assertIn(
            download_client.config["name"],
            repr(download_client),
            "Download client URL missing from Servarr representation",
        )

    def test_download_client_missing_port(self):
        """
        The download client informs the user with an error if the port can't be guessed.
        """
        self.runner.config = self.config
        download_client = prunerr.downloadclient.PrunerrDownloadClient(self.runner)
        with self.assertRaises(
            utils.PrunerrValidationError,
            msg="Download client URL without port did not raise and error",
        ):
            download_client.update({"url": "foo://transmission.example.com"})

    def test_download_client_missing_url(self):
        """
        The download client informs the user with an error if no url is configured.
        """
        download_client = prunerr.downloadclient.PrunerrDownloadClient(self.runner)
        with self.assertRaises(
            prunerr.utils.PrunerrValidationError,
            msg="Wrong missing config URL validation exception type",
        ) as exc_context:
            download_client.update({})
        self.assertIn(
            "must include a URL",
            str(exc_context.exception),
            "Wrong missing config URL validation error message",
        )
