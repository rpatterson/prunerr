#!/bin/bash

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

#
# Install into the local system all external tools required by recipes.  Must support
# running again on the same system.
#
# System OS packages:
# - `gettext`: We need `$ envsubst` in the `expand_template` `./Makefile` function
# - `py3-pip`: We need `$ pip3` to install the project's Python build tools
# - `docker-cli-compose`: Dependencies for which we can't get current versions otherwise

set -eu -o pipefail
shopt -s inherit_errexit
if [ "${DEBUG:=true}" = "true" ]
then
    # Echo commands for easier debugging
    PS4='$0:$LINENO+'
    set -x
fi


main() {
    if which apk
    then
        sudo apk update
        sudo apk add "gettext" "py3-pip" "docker-cli-compose"
    elif which apt-get
    then
        sudo apt-get update
        sudo apt-get install -y "gettext-base" "python3-pip" "docker-compose-plugin"
    else
        set +x
        echo "ERROR: OS not supported for installing system dependencies"
        # TODO: Add OS-X/Darwin support.
        false
    fi
    pip3 install -r "./build-host/requirements.txt.in"
# Manage JavaScript/TypeScript packages:
# https://github.com/nvm-sh/nvm#install--update-script
    if ! which nvm
    then
        wget -qO- \
            "https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.3/install.sh" \
            | bash
        set +x
        . ~/.nvm/nvm.sh || true
    fi
# The `./.nvmrc` is using latest stable version:
# https://github.com/nodejs/release#release-schedule
    set +x
    nvm install
    set -x
}


main "$@"
