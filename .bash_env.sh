#!/bin/bash

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

# Initialize bash for `./Makefile` reproducing user installs.

# Load NVM and use the right version of NPM:
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"

# Only echo commands for recipes, not `$(shell)`:
if (( "${MAKELEVEL}" > 0 ))
then
    set -x
fi
