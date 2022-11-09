"""
Prunerr interaction with download clients.
"""

import logging
import urllib.parse

import transmission_rpc

logger = logging.getLogger(__name__)


class PrunerrDownloadClient:
    """
    An individual, specific download client that Prunerr interacts with.
    """

    client = None

    def __init__(self, runner, config, servarr=None):
        """
        Capture a references to the runner and individual download client configuration.
        """
        self.runner = runner
        self.config = config
        self.servarrs = {}
        if servarr is not None:
            self.servarrs[servarr.servarr.config["url"]] = servarr

    def connect(self):
        """
        Connect to the download client's RPC client.
        """
        split_url = urllib.parse.urlsplit(self.config["url"])
        port = split_url.port
        if not port:
            if split_url.scheme == "http":
                port = 80
            elif split_url.scheme == "https":
                port = 443
            else:
                raise ValueError(f"Could not guess port from URL: {self.config['url']}")

        logger.debug(
            "Connecting to download client: %s",
            self.config["url"],
        )
        self.client = transmission_rpc.client.Client(
            protocol=split_url.scheme,
            host=split_url.hostname,
            port=port,
            path=split_url.path,
            username=split_url.username,
            password=split_url.password,
        )

        return self.client
