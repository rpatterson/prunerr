#!/bin/bash

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

# Perform any required volatile run time initialization

set -eu -o pipefail
shopt -s inherit_errexit
if test "${DEBUG:=false}" = "true"
then
    # Echo commands for easier debugging
    set -x
    PS4='$0:$LINENO+'
fi


main() {
    # Run as the user from the enironment, adding that user if necessary
    if test -n "${PUID:-}"
    then
        if (( $(id -u) != 0 ))
        then
            set +x
            echo "ERROR: Can't create a user when not run as root" 1>&2
            false
        fi
        # Add an unprivileged user:
        if ! getent group "${PGID}" >"/dev/null"
        then
            addgroup --gid "${PGID}" "${PROJECT_NAME}"
        fi
        group_name=$(getent group "${PGID}" | cut -d ":" -f 1)
        if ! id "${PUID}" >"/dev/null" 2>&1
        then
            # Add a user to the `passwd` DB to support looking up the
            # `~prunerr/` HOME directory:
            adduser --uid "${PUID}" --gid "${PGID}" --disabled-password \
                --gecos "Prunerr,,," "${PROJECT_NAME}" >"/dev/null"
        fi
        if tty_dev=$(tty)
        then
            # Fix interactive session terminal ownership:
            chown "${PUID}" "${tty_dev}"
        fi
        # Run the rest of the command-line arguments as the unprivileged user:
        exec gosu "${PUID}" "${@}"
    fi

    # Run un-altered as the user passed in by docker:
    exec "$@"
}


main "$@"
