#!/bin/ash

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

# Perform any set up only needed one time per CI job then delegate to `argv`.

set -eu -o pipefail
CHOWN_ARGS=""
if test "${DEBUG:=false}" = "true"
then
    # Echo commands for easier debugging
    set -x
    PS4='${0}:${LINENO}+'
    CHOWN_ARGS="${CHOWN_ARGS} -c"
fi


main() {
    # Add the user and group from the environment if necessary:
    if test -n "${PUID:-}"
    then
        if test "$(id -u)" != "0"
        then
            set +x
            echo "ERROR: Can't create a user when not run as root" 1>&2
            false
        fi

	# Ensure the home directory in the image has the correct permissions.  Change
	# permissions selectively to avoid time-consuming recursion:
	chown ${CHOWN_ARGS} "${PUID}:${PGID:-${PUID}}" "/home/runner/" \
	      /home/runner/.??* /home/runner/.local/* \
              "/home/runner/.local/state/${PROJECT_NAME}/" \
              "/home/runner/.local/state/${PROJECT_NAME}/log/"

        # Add an unprivileged user to cover those use cases and better match local
        # development:
        if ! getent group "${PGID}" >"/dev/null"
        then
            addgroup -g "${PGID}" "runner"
        fi
        group_name=$(getent group "${PGID}" | cut -d ":" -f 1)
        if ! id "${PUID}" >"/dev/null" 2>&1
        then
            adduser -u "${PUID}" -G "${group_name}" -g \
                "CI Runner,,,$(
                    git config -f "/home/runner/.gitconfig" "user.email"
                )" -D -s "/bin/bash" "runner"
        fi

        # Ensure the user can talk to `# dockerd`:
        user_name=$(getent passwd "${PUID}" | cut -d ":" -f 1)
        if test -e "/var/run/docker.sock"
        then
            docker_gid=$(stat -c "%g" "/var/run/docker.sock")
            if ! getent group ${docker_gid} >"/dev/null"
            then
                addgroup -g "${docker_gid}" "docker"
            fi
            if ! id -G "${user_name}" | grep -qw "${docker_gid}"
            then
                adduser "${user_name}" "$(stat -c "%G" "/var/run/docker.sock")"
            fi
        fi
    fi

    # Delegate to the rest of `argv`:
    exec "$@"
}


main "$@"
