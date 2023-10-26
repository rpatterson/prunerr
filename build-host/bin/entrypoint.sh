#!/bin/ash

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

# Shared set up for local testing of CI/CD

set -eu -o pipefail
if test "${DEBUG:=false}" = "true"
then
    # Echo commands for easier debugging
    set -x
    PS4='${0}:${LINENO}+'
fi


main() {
    # Run as the user from the environment:
    if test -n "${PUID:-}"
    then
        exec su-exec "${PUID}" "${@}"
    fi

    # Run un-altered as the user passed in by docker:
    exec "$@"
}


main "$@"
