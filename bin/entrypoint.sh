#!/bin/bash

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

# Perform any required volatile run time initialization

set -eu -o pipefail
shopt -s inherit_errexit
CHOWN_ARGS=""
if test "${DEBUG:=false}" = "true"
then
    # Echo commands for easier debugging
    set -x
    PS4='$0:$LINENO+'
    CHOWN_ARGS+="-c"
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

	# Ensure the home directory in the image has the correct permissions. Change
	# permissions selectively to avoid time-consuming recursion:
	chown ${CHOWN_ARGS} "${PUID}:${PGID}" "/home/${PROJECT_NAME}/" \
	      /home/${PROJECT_NAME}/.??* /home/${PROJECT_NAME}/.local/*

        # Add an unprivileged user:
        if ! getent group "${PGID}" >"/dev/null"
        then
            addgroup --gid "${PGID}" "prunerr"
        fi
        group_name=$(getent group "${PGID}" | cut -d ":" -f 1)
        if ! id "${PUID}" >"/dev/null" 2>&1
        then
            # Add a user to the `passwd` DB to support looking up the
            # `~prunerr/` HOME directory:
            adduser --uid "${PUID}" --gid "${PGID}" --disabled-password \
                --gecos "Prunerr,,," "prunerr" >"/dev/null"
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
