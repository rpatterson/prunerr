# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

# pylint: disable=magic-value-comparison,missing-any-param-doc,missing-param-doc
# pylint: disable=missing-return-doc,missing-return-type-doc,missing-type-doc

"""
Utility functions or other shared constants and values.

Useful to avoid circular imports.
"""

import sys
import os
import copy
import socket
import getpass
import json
import urllib.parse
import logging

import transmission_rpc
import arrapi

try:
    import ntfy
except ImportError:  # pragma: no cover
    ntfy = None  # type: ignore

try:
    # BBB: Python <3.10 compat
    import pathlib3x as pathlib  # pylint: disable=unused-import
except ImportError:  # pragma: no cover
    import pathlib  # type: ignore # pylint: disable=unused-import # noqa: F401

try:
    from functools import (  # type: ignore # pylint: disable=unused-import
        cached_property,
    )
except ImportError:  # pragma: no cover
    # BBB: Python <3.8 compatibility
    from backports.cached_property import cached_property  # type: ignore # noqa: F401

TRUE_STRS = {"1", "true", "yes", "on"}
DEBUG = (  # noqa: F841
    "DEBUG" in os.environ  # pylint: disable=magic-value-comparison
    and os.environ["DEBUG"].strip().lower() in TRUE_STRS
)
POST_MORTEM = (  # noqa: F841
    "POST_MORTEM" in os.environ  # pylint: disable=magic-value-comparison
    and os.environ["POST_MORTEM"].strip().lower() in TRUE_STRS
)

RETRY_EXC_TYPES = (
    ConnectionError,
    transmission_rpc.error.TransmissionError,
    arrapi.exceptions.ConnectionFailure,
    # Can be raised by `transmission_rpc` when deserializing JSON from an interrupted
    # response:
    ValueError,
    json.JSONDecodeError,
)


class PrunerrValidationError(Exception):
    """
    Incorrect Prunerr configuration.
    """


def normalize_url(url):
    """
    Return the given URL in the same form regardless of port or authentication.

    - Do *not* include a port if the port matches the scheme.
    - Strip the authentication password or passphrase.
    """
    url = urllib.parse.urlsplit(url)
    netloc = url.hostname
    if url.port and (
        (url.scheme == "http" and url.port != 80)
        or (url.scheme == "https" and url.port != 443)
    ):
        netloc = f"{netloc}:{url.port}"
    if url.username:
        netloc = f"{url.username}@{netloc}"
    return url._replace(netloc=netloc).geturl()


class DaemonOnceFilter(logging.Filter):  # pylint: disable=too-few-public-methods
    """
    Log a given message only once per daemon session, the first loop.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the record of which download items have been logged.
        """
        super().__init__(*args, **kwargs)

        self.download_hashes = set()

    def filter(self, record):
        """
        Check the record extra attributes to see if the runner has already looped once.
        """
        download_hash = getattr(record, "download_hash", None)
        if (
            (runner := getattr(record, "runner", None)) is not None
            and runner.quiet
            and download_hash is not None
            and download_hash in self.download_hashes
        ):
            return False
        self.download_hashes.add(download_hash)
        return True


daemon_once_filter = DaemonOnceFilter()


class TitleFormatter(logging.Formatter):
    """
    A formatter that also formats a ``title`` in addition to the main message.
    """

    def __init__(
        self,
        *args,
        title_fmt=(
            "%(user)s@%(hostname)s:%(cwd)s"
            " %(levelname)s %(name)s[%(process)d]: $ %(argv)s"
        ),
        fmt="%(message)s",
        **kwargs,
    ):
        """
        Set a default title and message formatting template.
        """
        super().__init__(fmt=fmt, *args, **kwargs)
        self.title_formatter = logging.Formatter(fmt=title_fmt)


title_formatter = TitleFormatter()


class NotifyHandler(logging.Handler):  # pylint: disable=too-few-public-methods
    """
    Log a given message only once per daemon session, the first loop.
    """

    def format(self, record):
        """
        Use a default formatter if none has been explicitly configured.
        """
        fmt = self.formatter if self.formatter else title_formatter
        return fmt.format(record)

    def format_title(self, record):
        """
        Format a title separately from the message.
        """
        fmt = self.formatter if self.formatter else title_formatter
        title_record = copy.copy(record)
        vars(title_record).update(
            exc_info=None,
            exc_text=None,
            stack_info=None,
        )
        return fmt.title_formatter.format(title_record)

    def emit(self, record):
        """
        Send a notification for the record using the user's ``ntfy`` configuration.
        """
        ntfy.notify(
            message=self.format(record),
            title=self.format_title(record),
        )

    def handle(self, record):
        """
        Add information about this process to the record.
        """
        # General process context:
        # Thans to `./checkouts/ntfy/ntfy/__init__.py` for some of this:
        vars(record).update(
            argv=" ".join(sys.argv),
            home=os.path.expanduser("~"),
            cwd=os.getcwd(),
            user=getpass.getuser(),
            hostname=socket.gethostname(),
        )
        if os.name != "nt" and record.cwd.startswith(record.home):  # pragma: no cover
            record.cwd = os.path.join("~", record.cwd[len(record.home) + 1 :])

        super().handle(record)


notify_handler = NotifyHandler()
notify_handler.setLevel(logging.ERROR)


class PrunerrComponent:
    """
    An object representing a part of the Prunerr and Servarr architecture.
    """

    def update(self):
        """
        Update cached values when this download item is updated.
        """
        self.clear()

    def clear(self):
        """
        Reset derived attributes cached in this instance.
        """
        for attr_name in list(vars(self).keys()):
            if isinstance(getattr(type(self), attr_name, None), cached_property):
                delattr(self, attr_name)
            elif hasattr(getattr(self, attr_name, None), "cache_clear"):
                getattr(self, attr_name).cache_clear()
