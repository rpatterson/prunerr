#!/bin/bash

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

# Run the Python kitchen sink linter as fast as possible.

set -eu -o pipefail
shopt -s inherit_errexit
PROSPECTOR_ARGS=
if test "${DEBUG:=false}" = "true"
then
    # Echo commands for easier debugging
    set -x
    PS4='$0:$LINENO+'
    PROSPECTOR_ARGS+=" -X"
fi


main() {
    git ls-files -co --exclude-standard -z '*.py' |
	xargs -0 -- prospector ${PROSPECTOR_ARGS} "${@}"
}


main "${@}"
