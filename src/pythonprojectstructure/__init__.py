"""
Python project structure foundation or template, top-level package.
"""

# Manage version through the VCS CI/CD process
__version__ = None
try:
    from . import version
except ImportError:  # pragma: no cover
    pass
else:  # pragma: no cover
    __version__ = version.version
