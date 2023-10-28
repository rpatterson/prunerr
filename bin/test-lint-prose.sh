#!/bin/bash

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

# Run prose linters implemented in Python.

set -eu -o pipefail
shopt -s inherit_errexit
if [ "${DEBUG:=false}" = "true" ]
then
    # Echo commands for easier debugging
    set -x
    PS4='$0:$LINENO+'
fi


main() {
    set -x
    git ls-files -z '*.rst' | xargs -r -0 -- proselint --config "./.proselintrc.json"
}


main "$@"
