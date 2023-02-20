"""
Test Prunerr's interaction with download clients.
"""
# Aggregate download client configurations from Servarr and the configuration file.

import os
import pathlib

from unittest import mock

import prunerr.runner
import prunerr.downloadclient

from .. import tests


@mock.patch.dict(os.environ, tests.PrunerrTestCase.ENV)
class PrunerrDownloadClientTests(tests.PrunerrTestCase):
    """
    Test the aggregation of download client configurations.
    """

    HOME = pathlib.Path(__file__).parent / "home" / "download-clients"
    CONFIG = HOME / ".config" / "prunerr.yml"
    ENV = dict(tests.PrunerrTestCase.ENV, HOME=str(HOME))

    RESPONSES_DIR = tests.PrunerrTestCase.RESPONSES_DIR.parent / "download-clients"

    SERVARR_DOWNLOAD_CLIENT_URLS = (
        # The usual case
        "http://transmission:secret@localhost:9091/transmission/",
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
        runner = prunerr.runner.PrunerrRunner(config=self.CONFIG)
        self.assertFalse(
            getattr(runner, "download_clients", None),
            "Download clients aggregated before `runner.update(...)`",
        )

        request_mocks = self.mock_responses()
        runner.update()
        self.assert_request_mocks(request_mocks)
        self.assertIn(
            "download_clients",
            dir(runner),
            "Download clients missing after `runner.update(...)`",
        )
        self.assertIsInstance(
            runner.download_clients,
            dict,
            "Wrong aggregated download clients type",
        )
        for download_client_url in self.DOWNLOAD_CLIENT_URLS:
            with self.subTest(download_client_url=download_client_url):
                self.assert_download_client(runner, download_client_url)

        # Ensure the same remote API/RPC client instances are used across download
        # client and servarr instance combinations to reduce requests and preserve any
        # caching the clients may do
        self.assertIs(
            runner.download_clients[self.SERVARR_DOWNLOAD_CLIENT_URLS[0]]
            .servarrs[self.config["servarrs"]["Sonarr"]["url"]]
            .servarr.client,
            runner.download_clients[self.SERVARR_DOWNLOAD_CLIENT_URLS[1]]
            .servarrs[self.config["servarrs"]["Sonarr"]["url"]]
            .servarr.client,
            "Servarr instance client not re-used across download clients",
        )
        self.assertIs(
            runner.servarrs[self.servarr_urls[0]]
            .download_clients[self.SERVARR_DOWNLOAD_CLIENT_URLS[0]]
            .download_client.client,
            runner.servarrs[self.servarr_urls[1]]
            .download_clients[self.SERVARR_DOWNLOAD_CLIENT_URLS[0]]
            .download_client.client,
            "Download client's RPC client not re-used across Servarr instances",
        )

    def assert_download_client(self, runner, download_client_url):
        """
        Confirm that an individual download client is configured correctly.
        """
        self.assertIn(
            download_client_url,
            runner.download_clients,
            "Aggregated download clients missing URL",
        )
        download_client = runner.download_clients[download_client_url]
        self.assertTrue(
            hasattr(download_client.client.session, "version"),
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
                if (
                    download_client.config["url"]
                    == self.SERVARR_DOWNLOAD_CLIENT_URLS[0]
                    or servarr_config["url"] == self.servarr_urls[0]
                ):
                    self.assertIn(
                        servarr_config["url"],
                        download_client.servarrs,
                        "Download client missing Servarr URL",
                    )
                else:
                    self.assertNotIn(
                        servarr_config["url"],
                        download_client.servarrs,
                        "Download client includes wrong Servarr URL",
                    )
                    continue
                servarr = download_client.servarrs[servarr_config["url"]]
                self.assertIn(
                    "config",
                    dir(servarr),
                    "Servarr instance missing config",
                )
                self.assertIsInstance(
                    servarr.config,
                    dict,
                    "Servarr instance wrong config type",
                )
                self.assertTrue(
                    servarr.config,
                    "Servarr instance empty config type",
                )
                self.assertIn(
                    "download_dir",
                    dir(servarr),
                    "Servarr instance missing download dir",
                )
                self.assertEqual(
                    servarr.download_dir,
                    self.tmp_path
                    / self.servarr_download_client_responses[servarr_config["url"]][0][
                        "fields"
                    ][7]["value"].lstrip(os.path.sep),
                    "Servarr instance wrong download dir",
                )

    def test_parallel_to(self):
        """
        Represent Servarr state in download item locations through parallel paths.
        """
        self.assertEqual(
            prunerr.downloaditem.parallel_to(
                self.downloaded_dir,
                self.downloaded_item,
                prunerr.downloadclient.PrunerrDownloadClient.SEEDING_DIR_BASENAME,
            ),
            self.seeding_item,
            "Wrong seeding directory for downloaded item",
        )
        self.assertEqual(
            prunerr.downloaditem.parallel_to(
                self.seeding_dir,
                self.servarr_downloaded_dir,
                "downloads",
            ),
            self.servarr_downloaded_dir,
            "Wrong downloaded directory for Servarr seeding directtory",
        )
        self.assertEqual(
            prunerr.downloaditem.parallel_to(
                self.downloaded_dir,
                self.servarr_seeding_dir,
                prunerr.downloadclient.PrunerrDownloadClient.SEEDING_DIR_BASENAME,
            ),
            self.servarr_seeding_dir,
            "Wrong seeding directory for downloaded item",
        )

    def test_download_client_repr(self):
        """
        The download client representation provides useful information for debugging.
        """
        runner = prunerr.runner.PrunerrRunner(config=self.CONFIG)
        download_client = prunerr.downloadclient.PrunerrDownloadClient(runner)
        download_client.config = {"url": self.download_client_urls[0]}
        self.assertIn(
            self.download_client_urls[0],
            repr(download_client),
            "Download client URL missing from Servarr representation",
        )

    def test_download_client_missing_port(self):
        """
        The download client informs the user with an error if the port can't be guessed.
        """
        runner = prunerr.runner.PrunerrRunner(config=self.CONFIG)
        runner.config = self.config
        download_client = prunerr.downloadclient.PrunerrDownloadClient(runner)
        with self.assertRaises(
            ValueError,
            msg="Download client URL without port did not raise and error",
        ):
            download_client.update({"url": "foo://transmission.example.com"})
