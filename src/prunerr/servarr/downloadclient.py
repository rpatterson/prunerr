# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Prunerr interaction with Servarr instances.
"""

import collections.abc
import datetime
import urllib.parse
import logging

import dateutil.parser

import prunerr.downloadclient
import prunerr.downloaditem
import prunerr.servarr.release
from .. import utils
from ..utils import pathlib
from ..utils import cached_property
from . import release as release_module

logger = logging.getLogger(__name__)

API_FIELDS_VALUE_KEY = "value"


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

    @property
    def details(self) -> dict:
        """
        Assemble all available useful information.

        :return: Map descriptive names to useful values.
        """
        return {
            "servarr": self.servarr.config.get("name"),
            "dowload_client": (
                self.download_client.config["name"]
                if hasattr(self, "download_client")
                else self.config.get("url")
            ),
        }

    def update(self, config: dict):  # type: ignore # pylint: disable=arguments-differ
        """
        Update download client configuration specific to this Servarr instance.

        :param config: The de-serialized Servarr API ``downloadclient`` endpoint JSON.
        """
        super().update()
        self.config = config
        # Assemble the download client paths managed by Servarr
        self.download_dir = pathlib.Path(
            self.config["fieldValues"][self.servarr.type_map["download_dir_field"]]
        ).resolve()

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

    @cached_property
    def releases(self) -> list:
        """
        Wrap the download items managed by this Servarr instance as releases.

        :return: The download items wrapped as releases specific to this instance.
        """
        releases = []
        for download_item in self.download_client.items:
            # Ensure this release instance and this download item instance are
            # associated no matter which direction they came from:
            if (release := vars(download_item).get("release")) is None:
                release = prunerr.servarr.release.PrunerrServarrRelease(
                    self,
                    download_item,
                )
                download_item.release = release
            releases.append(release)
        return releases

    def filter_seeding(self) -> collections.abc.Generator:
        """
        Filter releases that have been acted on by Servarr.

        All download items that are seeding, that are in this Servarr instance's
        download directory, and aren't in this Servarr instance's queue.  Also only
        include items that have some Servarr history events other than `grabbed` to
        prevent moving manually grabbed items out from under Servarr before it's had a
        chance to recognize notice them.

        :return: The ``prunerr.downloaditem.PrunerrDownloadItem()`` instances.
        """
        # Avoid attribute and item lookup in the inner loop:
        download_dir = self.download_dir
        event_type_grabbed = self.servarr.EVENT_TYPE_GRABBED
        now = datetime.datetime.now(datetime.timezone.utc)
        dateutil_parse = dateutil.parser.parse
        daemon_poll = datetime.timedelta(
            seconds=self.servarr.runner.config["daemon"]["poll"],
        )

        for download_item in self.download_client.items:
            if (
                # Skip items not in this Servarr instance's download directory for this
                # download client:
                download_dir == download_item.download_dir
                # Skip items known by a Servarr instance in it's queue:
                and download_item.hashString.upper() not in self.servarr.queue
            ):
                for history_record in download_item.release.history:
                    if history_record["eventType"] != event_type_grabbed:
                        break
                    pass  # pragma: no cover  # pylint: disable=unnecessary-pass
                else:
                    history_record = None  # pragma: no cover
                if (
                    # Skip items with no history other than `grabbed` events:
                    history_record is not None
                    # Skip items whose most recent history other than `grabbed`, such as
                    # `downloadFolderimported`, is too recent to avoid moving out from
                    # under Servarr:
                    # TODO: Make timezone aware:
                    # TODO: Add a separate configuration key for the wait period:
                    and (now - dateutil_parse(history_record["date"])) > daemon_poll
                ):
                    yield download_item
                else:
                    pass  # pragma: no cover

    def delete(
        self, release: "prunerr.servarr.release.PrunerrServarrRelease", **params
    ):
        """
        Delete a release from the Servarr queue.

        :param release: The Servarr release to delete.
        :param params: Additional parameters to pass onto the Servarr API endpoint
            request.
        """
        self.servarr.client.delete(
            f"queue/{release.queue[0].get('id')}",
            **params,
        )


def deserialize_servarr_download_client(download_client_config: dict) -> dict:
    """
    Assemble field values and a URL for a Servarr download client configuration.

    :param download_client_config: The download client settings from the Servarr API.
    :return: The ``download_client_config`` augmented with the field values.
    """
    download_client_config["fieldValues"] = {
        download_client_config_field["name"]: download_client_config_field["value"]
        for download_client_config_field in download_client_config["fields"]
        if API_FIELDS_VALUE_KEY in download_client_config_field
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
