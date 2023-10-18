#!/bin/bash

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

# Add files tracked in VCS for any bind volume paths that have none.
#
# Useful so that `# dockerd` doesn't create them as `root`.

set -eu -o pipefail
shopt -s inherit_errexit
if test "${DEBUG:=false}" = "true"
then
    # Echo commands for easier debugging
    set -x
    PS4='$0:$LINENO+'
fi


main() {
    source_prefix="${1}"
    shift
    target_prefix="${1}"
    shift

    docker_services="$(sed -nE 's#^  ([^ :]+): *$#\1#p' ./docker-compose*.yml)"
    (
	docker compose config ${docker_services} |
	    sed -nE -e "s#^ *source: *${source_prefix}/(.+)#\1#p" &&
	    docker compose config ${docker_services} |
	        sed -nE -e "s#^ *target: *${target_prefix}/(.+)#\1#p"
    ) | sort | uniq | while read "docker_volume_path"
    do
	if test -n "$(git ls-files "${docker_volume_path}")"
	then
	    continue
	fi
	docker_volume_added="true"
	mkdir -pv "${docker_volume_path}"
	cat <<"EOF" >"${docker_volume_path}/.gitignore"
# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

# Ensure the Docker volume exists so `# dockerd` doesn't create this as root:
/*
!.git*
!/Makefile
/*~
EOF
	git add -f "${docker_volume_path}/.gitignore"
	echo "${docker_volume_path}/.gitignore"
    done
}


main "$@"
