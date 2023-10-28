#!/usr/bin/env python

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

# PYTHON_ARGCOMPLETE_OK

# https://kislyuk.github.io/argcomplete/#global-completion
"""
Run from the command-line by using Python's `-m` option.
"""

import sys

from . import main

sys.exit(main())
