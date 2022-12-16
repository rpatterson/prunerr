"""
Python project structure foundation or template, top-level package.
"""

# TEMPLATE: Projects using this template should remove the linter disable/ignore
# comments and use `utils` as appropriate for the project.
from . import utils  # noqa: F401, pylint: disable=unused-import

# Manage version through the VCS CI/CD process
__version__ = None
try:
    from . import version
except ImportError:  # pragma: no cover
    pass
else:  # pragma: no cover
    __version__ = version.version
