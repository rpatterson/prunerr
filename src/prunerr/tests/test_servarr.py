"""
Test Prunerr's interaction with Servarr instances.
"""

import os

from unittest import mock

import prunerr.servarr

from .. import tests


@mock.patch.dict(os.environ, tests.PrunerrTestCase.ENV)
class PrunerrServarrTests(
    tests.PrunerrTestCase,
):  # pylint: disable=too-few-public-methods
    """
    Test Prunerr's interaction with Servarr instances.
    """

    def test_servarr_repr(self):
        """
        The Servarr representations provide useful information for debugging.
        """
        runner = prunerr.runner.PrunerrRunner(config=self.CONFIG)
        servarr = prunerr.servarr.PrunerrServarrInstance(runner)
        servarr.config = {"name": list(self.config["servarrs"].keys())[0]}
        self.assertIn(
            servarr.config["name"],
            repr(servarr),
            "Servarr name missing from Servarr representation",
        )
        servarr_download_client = prunerr.servarr.PrunerrServarrDownloadClient(servarr)
        servarr_download_client.download_client = (
            prunerr.downloadclient.PrunerrDownloadClient(runner)
        )
        servarr_download_client.download_client.config = {
            "url": self.download_client_urls[0],
        }
        self.assertIn(
            servarr.config["name"],
            repr(servarr_download_client),
            "Servarr name missing from Servarr representation",
        )
        self.assertIn(
            self.download_client_urls[0],
            repr(servarr_download_client),
            "Download client URL missing from Servarr representation",
        )
