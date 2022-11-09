"""
Run Prunerr commands across multiple Servarr instances and download clients.
"""

import logging


import prunerr.downloadclient
import prunerr.servarr

logger = logging.getLogger(__name__)


class PrunerrRunner:
    """
    Run Prunerr sub-commands across multiple Servarr instances and download clients.
    """

    download_clients = None
    servarrs = None

    def __init__(self, config):
        """
        Capture a reference to the global Prunerr configuration.
        """
        self.config = config

    # @tenacity.retry(
    #     retry=tenacity.retry_if_exception_type(
    #         (
    #             socket.error,
    #             transmission_rpc.error.TransmissionError,
    #             arrapi.exceptions.ConnectionFailure,
    #         )
    #     ),
    #     wait=tenacity.wait_fixed(1),
    #     reraise=True,
    #     before_sleep=tenacity.before_sleep_log(logger, logging.DEBUG),
    # )
    def connect(self):
        """
        Connect to the download and Servarr clients, waiting for reconnection on error.

        Aggregate all download clients from all Servarr instances defined in the config.
        """
        self.download_clients = {}

        # Start with download clients not connected to a Servarr instance so that if
        # Servarr instances are connected to the same download client, the reference to
        # the servarr instance takes precedence.
        for download_client_url in self.config.get("download-clients", {}).get(
            "urls", []
        ):
            self.download_clients[
                download_client_url
            ] = prunerr.downloadclient.PrunerrDownloadClient(
                self,
                {"url": download_client_url},
            )
            self.download_clients[download_client_url].connect()

        # Gather download clients from Servarr configuration via the Servarr API
        self.servarrs = {}
        for servarr_config in self.config.get("servarrs", {}).values():
            self.servarrs[
                servarr_config["url"]
            ] = servarr = prunerr.servarr.PrunerrServarrInstance(self, servarr_config)
            servarr.connect()
            self.download_clients.update(
                (item[0], item[1].download_client)
                for item in servarr.download_clients.items()
            )

        return self.download_clients
