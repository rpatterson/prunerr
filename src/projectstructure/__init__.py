# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Project structure foundation or template, top-level package.
"""

# TEMPLATE: Projects using this template should remove the linter disable/ignore
# comments and use `utils` as appropriate for the project.
from . import utils  # pylint: disable=unused-import,useless-suppression

# Manage version through the VCS CI/CD process
__version__ = None
try:
    from . import version
except ImportError:  # pragma: no cover
    pass
else:  # pragma: no cover
    __version__ = version.version
