#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
# https://kislyuk.github.io/argcomplete/#global-completion
"""
Execute CLI via Python's `-m` option.
"""

import sys

from . import main

sys.exit(main())
