# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

# pylint: disable=magic-value-comparison,missing-any-param-doc,missing-param-doc
# pylint: disable=missing-return-doc,missing-return-type-doc,missing-type-doc

"""
Utility functions or other shared constants and values.

Useful to avoid circular imports.
"""

import os
import socket
import json
import urllib.parse
import logging

import transmission_rpc
import arrapi

try:
    # BBB: Python <3.10 compat
    import pathlib3x as pathlib  # pylint: disable=unused-import
except ImportError:  # pragma: no cover
    import pathlib  # type: ignore # pylint: disable=unused-import

try:
    from functools import (  # type: ignore # pylint: disable=unused-import
        cached_property,
    )
except ImportError:  # pragma: no cover
    # BBB: Python <3.8 compatibility
    from backports.cached_property import cached_property  # type: ignore

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
    socket.error,
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

    def filter(self, record):
        """
        Check the record extra attributes to see if the runner has already looped once.
        """
        if (runner := getattr(record, "runner", None)) is not None:
            return not runner.quiet
        return True


daemon_once_filter = DaemonOnceFilter()
