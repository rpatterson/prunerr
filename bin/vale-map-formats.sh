#!/bin/bash

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

# Map extensions from code files in VCS not supported by Vale for use in `[formats]`.

set -eu -o pipefail
shopt -s inherit_errexit
if [ "${DEBUG:=}" = "true" ]
then
    # Echo commands for easier debugging
    PS4='$0:$LINENO+'
    set -x
fi


main() {
    git ls-files -co --exclude-standard -z |
    while read -d $'\0'
    do
        file_name="$(basename "${REPLY}")" &&
    	  if echo "${file_name}" | grep -Eq '[^.]\.'
    	  then
            echo "${file_name##*.}"
    	  fi
    done | grep -Ev \
    '^c|h|cs|csx|cpp|cc|cxx|hpp|css|go|hs|java|bsh|js|less|lua|pl|pm|pod|php|ps1|py|py3|pyw|pyi|rpy|r|R|rb|rs|sass|scala|sbt|swift|txt|license$' \
    | sort | uniq | sed -nE 's|(.+)|\1 = pl|p'
}


main "$@"
