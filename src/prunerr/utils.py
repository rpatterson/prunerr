# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT


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
import html
import logging

import transmission_rpc
import arrapi

import appdirs
from ruamel import yaml

try:
    import ntfy
except ImportError:  # pragma: no cover
    ntfy = None  # type: ignore
else:
    import ntfy.default_config

try:
    # BBB: Python <3.10 compat
    import pathlib3x as pathlib  # pylint: disable=unused-import
except ImportError:  # pragma: no cover
    import pathlib  # pylint: disable=unused-import # noqa: F401

try:
    from functools import (
        cached_property,
    )
except ImportError:  # pragma: no cover
    # BBB: Python <3.8 compatibility
    from backports.cached_property import cached_property  # type: ignore

TRUE_STRS = {"1", "true", "yes", "on"}
DEBUG_STR = "DEBUG"
DEBUG = DEBUG_STR in os.environ and os.environ["DEBUG"].strip().lower() in TRUE_STRS
POST_MORTEM_STR = "POST_MORTEM"
POST_MORTEM = (
    POST_MORTEM_STR in os.environ
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

URL_SCHEME_HTTP = "http"
URL_SCHEME_HTTPS = "https"
URL_PORT_HTTP = 80
URL_PORT_HTTPS = 443

OS_NAME_NT = "nt"


class PrunerrValidationError(Exception):
    """
    Incorrect Prunerr configuration.
    """


def normalize_url(url_str: str) -> str:
    """
    Return the given URL in the same form regardless of port or authentication.

    - Do *not* include a port if the port matches the scheme.
    - Strip the authentication password or passphrase.

    :param url_str: The URL before normalization.
    :return: The normalized URL.
    :raises ValueError: Something is wrong with the given URL.
    """
    url = urllib.parse.urlsplit(url_str)
    if (netloc := url.hostname) is None:
        raise ValueError(f"URL missing hostname: {url_str}")  # pragma: no cover
    if url.port and (
        (url.scheme == URL_SCHEME_HTTP and url.port != URL_PORT_HTTP)
        or (url.scheme == URL_SCHEME_HTTPS and url.port != URL_PORT_HTTPS)
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

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Check the record extra attributes to see if the runner has already looped once.

        :param record: The log message.
        :return: Whether or not to emit this log message.
        """
        download_hash = getattr(record, "download_hash", None)
        if (
            (runner := getattr(record, "runner", None)) is not None
            and runner.quiet
            and hasattr(record, "download_hash")
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


class ProcessLogRecord(logging.LogRecord):  # pylint: disable=too-few-public-methods
    """
    A log message record augmented with context about this process.
    """

    def __init__(self, *args, **kwargs):
        """
        Also add the process context.
        """
        super().__init__(*args, **kwargs)

        # General process context:
        # Thans to `./checkouts/ntfy/ntfy/__init__.py` for some of this:
        self.argv = " ".join(sys.argv)
        self.home = os.path.expanduser("~")
        self.cwd = os.getcwd()
        self.user = getpass.getuser()  # noqa: V101
        self.hostname = socket.gethostname()
        if os.name != OS_NAME_NT and self.cwd.startswith(self.home):  # pragma: no cover
            self.cwd = os.path.join("~", self.cwd[len(self.home) + 1 :])


class NotifyHandler(logging.Handler):
    """
    Log a given message only once per daemon session, the first loop.
    """

    NTFY_BACKEND_MATRIX = "matrix"

    formatter: TitleFormatter

    def __init__(self, *args, **kwargs):
        """
        Prepare anything specific to ``ntfy`` backends.
        """
        super().__init__(*args, **kwargs)

    @cached_property
    def ntfy_config(self) -> dict:
        """
        Deserialize the user's ``ntfy`` configuration.

        :return: The deserialized ``ntfy`` YAML configuration.
        """
        # Unfortunately, `ntfy.config.load_config()` leaks the file handle for the
        # configuration file so deserialize the configuration ourselves:
        config_path = pathlib.Path(
            appdirs.user_config_dir("ntfy", "dschep"), "ntfy.yml"
        ).expanduser()
        if config_path.exists():
            yaml_loader = yaml.YAML(typ="safe", pure=True)
            with open(config_path, encoding="utf-8") as ntfy_config_opened:
                return yaml_loader.load(ntfy_config_opened)
        return ntfy.default_config.config  # pragma: no cover

    def format(self, record: logging.LogRecord) -> str:
        """
        Use a default formatter if none has been explicitly configured.

        :param record: The log message to format.
        :return: The formatted log message.
        """
        fmt = self.formatter if self.formatter else title_formatter
        return fmt.format(record)

    def format_title(self, record: logging.LogRecord) -> str:
        """
        Format a title separately from the message.

        :param record: The log message to format a title for.
        :return: The formatted notification title.
        """
        fmt = self.formatter if self.formatter else title_formatter
        title_record = copy.copy(record)
        vars(title_record).update(
            exc_info=None,
            exc_text=None,
            stack_info=None,
        )
        return fmt.title_formatter.format(title_record)

    def emit(self, record: logging.LogRecord):
        """
        Send a notification for the record using the user's ``ntfy`` configuration.

        Both the formatted title and the formatted message are escaped using
        ``html.escape()``.

        :param record: The log message to send a notification for.
        """
        title = self.format_title(record)
        message = self.format(record)
        if self.NTFY_BACKEND_MATRIX in self.ntfy_config.get("backends", ["default"]):
            # Unfortunately, `ntfy` doesn't provide a way to pass in both the plain and
            # HTML versions of Matrix messages, so we either have to live with ugly HTML
            # formatting or hard-code a Matrix-specific format:
            title = html.escape(title)
            message = f"<pre>{html.escape(message)}</pre>"
        else:
            pass  # pragma: no cover
        ntfy.notify(title=title, message=message)

    def handle(self, record: logging.LogRecord) -> bool:
        """
        Add information about this process to the record.

        :param record: The log message to add information for.
        :return: Whether the message was emitted or not.
        """
        return super().handle(
            ProcessLogRecord(
                record.name,
                record.levelno,
                record.pathname,
                record.lineno,
                record.msg,
                record.args,
                record.exc_info,
                func=record.funcName,
                sinfo=record.stack_info,
            ),
        )


notify_handler = NotifyHandler()
notify_handler.setLevel(logging.ERROR)


class PrunerrComponent:
    """
    An object representing a part of the Prunerr and Servarr architecture.
    """

    @property
    def details(self) -> dict:
        """
        Assemble all available useful information.

        :return: Map descriptive names to useful values.
        """
        return {"id": id(self)}  # pragma: no cover

    def __repr__(self) -> str:
        """
        Readable, informative, and specific representation to ease debugging.
        """
        details_str = " ".join(
            f"{attr}={value!r}" for attr, value in self.details.items()
        )
        return f"<{type(self).__name__} {details_str}>"

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


class PrunerrOperationsItem(PrunerrComponent):
    """
    An item to which life-cycle stage operations are applied.
    """

    hashString: str  # noqa: N815

    @cached_property
    def log_path(self) -> pathlib.Path:
        """
        Assemble the path for the log file dedicated to this individual item.

        :raises NotImplementederror: A subclass doesn't override something.
        """
        raise NotImplementedError(
            "Subclasses must override ``log_path``"
        )  # pragma: no cover


def format_size(size: int) -> str:
    """
    Format a size in a form that is readable for humans.

    :param size: The size to format in bytes.
    :return: The human readable format.
    """
    number, unit = transmission_rpc.utils.format_size(size)
    return f"{number:0.2f} {unit}"
