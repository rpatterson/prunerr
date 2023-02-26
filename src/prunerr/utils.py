"""
Utility functions or other shared constants and values.

Particularly useful to avoid circular imports.
"""

import os
import logging

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
    "DEBUG" in os.environ and os.environ["DEBUG"].strip().lower() in TRUE_STRS
)
POST_MORTEM = (  # noqa: F841
    "POST_MORTEM" in os.environ
    and os.environ["POST_MORTEM"].strip().lower() in TRUE_STRS
)


class DaemonOnceFilter(logging.Filter):  # pylint: disable=too-few-public-methods
    """
    Log a given message only once per daemon session, the first loop.
    """

    def filter(self, record):
        """
        Check the record extra attributes to see if the runner has already looped once.
        """
        runner = getattr(record, "runner", None)
        if runner is not None:
            return not runner.quiet
        return True


daemon_once_filter = DaemonOnceFilter()
