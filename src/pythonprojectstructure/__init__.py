"""
Python project structure foundation or template, top-level package.
"""

# Manage version through the VCS CI/CD process
try:
    from . import version
except ImportError:  # pragma: no cover
    version = None
if version is not None:  # pragma: no cover
    __version__ = version.version

from .__main__ import *  # noqa
