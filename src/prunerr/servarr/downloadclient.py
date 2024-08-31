# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

# pylint: disable=magic-value-comparison,missing-any-param-doc,missing-param-doc
# pylint: disable=missing-raises-doc,missing-return-doc,missing-return-type-doc
# pylint: disable=missing-type-doc,missing-yield-doc,missing-yield-type-doc

"""
Prunerr interaction with Servarr instances.
"""

import time
import datetime
import urllib.parse
import logging

import dateutil

import prunerr.downloadclient
import prunerr.downloaditem
import prunerr.servarr.release
from .. import utils
from ..utils import pathlib
from . import release as release_module

logger = logging.getLogger(__name__)


class PrunerrServarrDownloadClient(utils.PrunerrComponent):
    """
    A specific Servar instance's individual specific download client.
    """

    RELEASE_FACTORY = release_module.PrunerrServarrRelease

    download_client: prunerr.downloadclient.PrunerrDownloadClient
    download_dir: pathlib.Path
    download_dir_suffix: pathlib.Path
    seeding_dir: pathlib.Path

    def __init__(self, servarr):
        """
        Capture references to the servarr instance and download client.
        """
        self.servarr = servarr
        self.config = {}

    def __repr__(self):
        """
        Readable, informative, and specific representation to ease debugging.
        """
        return (
            f"<{type(self).__name__} {self.servarr.config.get('name')!r}"
            f"->{self.config.get('url')!r}>"
        )

    def update(self, config):  # pylint: disable=arguments-differ
        """
        Update download client configuration specific to this Servarr instance.
        """
        super().update()
        self.config = config
        # Assemble the download client paths managed by Servarr
        self.download_dir = pathlib.Path(
            self.config["fieldValues"][self.servarr.type_map["download_dir_field"]]
        ).resolve()
        return self.download_dir

    def update_download_client(
        self,
        download_client: prunerr.downloadclient.PrunerrDownloadClient,
    ):
        """
        Update from the download client session data once available.

        :param download_client: The download client after getting the session.
        """
        self.download_dir_suffix = pathlib.Path(
            *self.download_dir.relative_to(
                download_client.download_dir.parent,
            ).parts[1:],
        )
        self.seeding_dir = pathlib.Path(
            download_client.download_dir.parent,
            download_client.SEEDING_DIR_BASENAME,
            self.download_dir_suffix,
        )

    def add_torrent(self, download_url, **kwargs):
        """
        Add a torrent to the download client and update instance state.

        :param download_url: The URL from which to download the torrent to add.
        :return: The added ``prunerr.downloaditem.PrunerrDownloadItem()`` instance.
        """
        added_item = prunerr.servarr.release.PrunerrServarrRelease(
            self,
            self.download_client.add_torrent(download_url, **kwargs),
        )
        return added_item

    def move(self, move_timeout=5 * 60):
        """
        Move download items that have been acted on by Servarr into the seeding dir.

        Move all download items that are seeding, that are in this Servarr instance's
        download directory, and aren't in this Servarr instance's queue.  Also only
        include items that have some Servarr history events other than `grabbed` to
        prevent moving manually grabbed items out from under Servarr before it's had a
        chance to recognize notice them.
        """
        download_items = [
            download_item
            for download_item in self.download_client.items
            # Skip items still downloading
            if download_item.status == "seeding"
            # Skip items known by a Servarr instance in it's queue
            and download_item.hashString.upper() not in self.servarr.queue
            # Skip items not in this Servarr instance's download directory for this
            # download client
            and self.download_dir in download_item.path.parents
            # Skip items with no history other than `grabbed` events:
            and download_item.release.history[0]["eventType"] != "grabbed"
            # Skip items whose most recent history other than `grabbed`, such as
            # `downloadFolderimported`, is too recent to avoid moving out from under
            # Servarr:
            # TODO: Make timezone aware:
            # TODO: Add a separate configuration key for the wait period:
            and (
                datetime.datetime.now(datetime.timezone.utc)
                - dateutil.parser.parse(download_item.release.history[0]["date"])
            )
            > datetime.timedelta(seconds=self.servarr.runner.config["daemon"]["poll"])
        ]
        if not download_items:
            logger.debug(
                "No %s download items to move",
                self.servarr.config["name"],
            )
            return None
        logger.info(
            "Moving download items: %r -> %r\n  %s",
            str(self.download_dir),
            str(self.seeding_dir),
            "\n  ".join(repr(download_item) for download_item in download_items),
        )
        self.download_client.client.move_torrent_data(
            ids=[download_item.hashString for download_item in download_items],
            location=self.seeding_dir,
        )
        # Wait for a timeout for items to finish moving before proceeding.
        start = time.time()
        while next(  # pylint: disable=while-used
            (
                download_item
                for download_item in download_items
                if download_item.path.exists()
            ),
            None,
        ):
            if time.time() - start > move_timeout:
                raise prunerr.downloadclient.DownloadClientTimeout(
                    f"Timed out waiting for {self.servarr.config['name']} items "
                    "to finish moving",
                )
            time.sleep(1)
        # Update the download item's dir for subsequent operations, done manually to
        # minimize requests.
        for download_item in download_items:
            download_item._fields[download_item.DOWNLOAD_DIR_FIELD] = (
                download_item._fields[download_item.DOWNLOAD_DIR_FIELD]._replace(
                    value=self.seeding_dir
                )
            )
            download_item.clear()
        return [download_item.hashString for download_item in download_items]

    def delete(self, release, **params):
        """
        Delete a release from the Servarr queue.
        """
        return self.servarr.client.delete(
            f"queue/{release.queue[0].get('id')}",
            **params,
        )


def deserialize_servarr_download_client(download_client_config):
    """
    Assemble field values and a URL for a Servarr download client configuration.
    """
    download_client_config["fieldValues"] = {
        download_client_config_field["name"]: download_client_config_field["value"]
        for download_client_config_field in download_client_config["fields"]
        if "value" in download_client_config_field
    }
    netloc = f"{download_client_config['fieldValues']['host']}"
    if download_client_config["fieldValues"].get("port") is not None:
        netloc = f"{netloc}:{download_client_config['fieldValues']['port']}"
    if download_client_config["fieldValues"].get("username"):
        netloc = f"{download_client_config['fieldValues']['username']}@{netloc}"
    download_client_config["url"] = urllib.parse.SplitResult(
        "http" if not download_client_config["fieldValues"]["useSsl"] else "https",
        netloc,
        download_client_config["fieldValues"]["urlBase"],
        "",
        "",
    ).geturl()
    return download_client_config
