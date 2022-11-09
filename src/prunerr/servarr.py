"""
Prunerr interaction with Servarr instances.
"""

import logging
import urllib.parse
import pathlib

import arrapi

import prunerr.downloadclient

logger = logging.getLogger(__name__)


class PrunerrServarrInstance:
    """
    An individual, specific Servarr instance that Prunerr interacts with.
    """

    # Map the different Servarr applications type terminology
    SERVARR_TYPE_MAPS = dict(
        sonarr=dict(
            # The top-level containing type, if applicable.  IOW, the type of items in
            # the top-level listing of the Servarr UI.  This is series for Sonarr as
            # contrasted with episode or season.  This is movie for Radarr.
            dir_type="series",
            # File vs item is a little confusing.  Item refers to episodes/movies as
            # contrasted with the `dir_type`.  But an episode/movie may comprise of
            # multiple files and a file may contain multiple episodes.
            item_type="episode",
            file_has_multi=True,
            client=arrapi.SonarrAPI,
            download_dir_field="tvDirectory",
            rename_template=(
                "{series[title]} - {episode[seasonEpisode]} - {episode[title]}"
            ),
        ),
        radarr=dict(
            dir_type="movie",
            item_type="movie",
            file_has_multi=False,
            client=arrapi.RadarrAPI,
            download_dir_field="movieDirectory",
            rename_template="{movie[title]} ({movie[release_year]})",
        ),
    )

    client = None
    get = None
    download_clients = None

    def __init__(self, runner, config):
        """
        Capture a references to the runner and individual Servarr configuration.
        """
        self.runner = runner
        self.config = config

    def connect(self):
        """
        Connect to the Servarr API client and lookup any download clients it defines.
        """
        logger.debug(
            "Connecting to Servarr instance: %s",
            self.config["url"],
        )
        self.client = self.SERVARR_TYPE_MAPS[self.config["type"]]["client"](
            self.config["url"],
            self.config["api-key"],
        )
        self.get = self.client._raw._get  # pylint: disable=protected-access

        self.download_clients = {}
        logger.debug(
            "Requesting Servarr download clients settings: %r",
            self.config["url"],
        )
        for download_client_config in self.get("downloadclient"):
            if not download_client_config["enable"]:
                continue
            download_client_config["fieldValues"] = {
                download_client_config_field["name"]: download_client_config_field[
                    "value"
                ]
                for download_client_config_field in download_client_config["fields"]
                if "value" in download_client_config_field
            }
            netloc = (
                f"{download_client_config['fieldValues']['host']}:"
                f"{download_client_config['fieldValues']['port']}"
            )
            if download_client_config["fieldValues"].get("username"):
                if download_client_config["fieldValues"].get("password"):
                    netloc = (
                        f"{download_client_config['fieldValues']['username']}:"
                        f"{download_client_config['fieldValues']['password']}@"
                        f"{netloc}"
                    )
                else:
                    netloc = (
                        f"{download_client_config['fieldValues']['username']}@{netloc}"
                    )
            download_client_config["url"] = urllib.parse.SplitResult(
                "http"
                if not download_client_config["fieldValues"]["useSsl"]
                else "https",
                netloc,
                download_client_config["fieldValues"]["urlBase"],
                None,
                None,
            ).geturl()
            self.download_clients[
                download_client_config["url"]
            ] = PrunerrServarrDownloadClient(
                servarr=self, config=download_client_config
            )
            self.download_clients[download_client_config["url"]].connect()

        return self.client


class PrunerrServarrDownloadClient:
    """
    A specific Servar instance's individual specific download client.
    """

    download_client = None

    def __init__(self, servarr, config):
        """
        Capture a references to the servarr instance and download client.
        """
        self.servarr = servarr
        self.config = config
        self.download_dir = pathlib.Path(
            self.config["fieldValues"][
                self.servarr.SERVARR_TYPE_MAPS[self.servarr.config["type"]][
                    "download_dir_field"
                ]
            ]
        ).resolve()

    def connect(self):
        """
        Connect to the download client's RPC client.
        """
        if self.config["url"] in self.servarr.runner.download_clients:
            self.download_client = self.servarr.runner.download_clients[
                self.config["url"]
            ]
            self.download_client.servarrs[self.servarr.config["url"]] = self
        else:
            self.download_client = prunerr.downloadclient.PrunerrDownloadClient(
                self.servarr.runner,
                self.config,
                servarr=self,
            )
            self.download_client.connect()
        return self.download_client
