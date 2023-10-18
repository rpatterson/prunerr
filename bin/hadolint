#!/bin/bash

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

# Wrapper for running the Dockerfile linter in a container.

set -eu -o pipefail
shopt -s inherit_errexit
if test -n "${DEBUG:=}"
then
    # Echo commands for easier debugging
    PS4='$0:$LINENO+'
    set -x
fi


main() {
    # Delegate to the container
    exec docker compose run --rm hadolint "$@"
}


main "$@"
