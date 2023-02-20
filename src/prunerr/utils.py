"""
Utility functions or other shared constants and values.

Particularly useful to avoid circular imports.
"""

import os

TRUE_STRS = {"1", "true", "yes", "on"}
DEBUG = (  # noqa: F841
    "DEBUG" in os.environ and os.environ["DEBUG"].strip().lower() in TRUE_STRS
)
POST_MORTEM = (  # noqa: F841
    "POST_MORTEM" in os.environ
    and os.environ["POST_MORTEM"].strip().lower() in TRUE_STRS
)
