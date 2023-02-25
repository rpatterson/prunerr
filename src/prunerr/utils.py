"""
Utility functions or other shared constants and values.

Particularly useful to avoid circular imports.
"""

import os

try:
    # BBB: Python <3.10 compat
    import pathlib3x as pathlib  # pylint: disable=unused-import
except ImportError:  # pragma: no cover
    import pathlib  # pylint: disable=unused-import

try:
    from functools import cached_property  # pylint: disable=unused-import
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
