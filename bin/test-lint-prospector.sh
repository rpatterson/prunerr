#!/bin/bash

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

# Run the Python kitchen sink linter as fast as possible.

set -eu -o pipefail
shopt -s inherit_errexit
if test "${DEBUG:=false}" = "true"
then
    # Echo commands for easier debugging
    set -x
    PS4='$0:$LINENO+'
fi


main() {
    git ls-files -co --exclude-standard -z '*.py' | xargs -0 -- prospector "${@}"
}


main "${@}"
