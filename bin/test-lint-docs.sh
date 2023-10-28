#!/bin/bash

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

# Run documentation linters implemented in Python.

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

    sphinx_buildername="${1:-html}"
    shift || true

    # TODO: Audit what checks all tools perform and remove redundant tools.

    # Verify reStructuredText syntax. Exclude `./docs/index.rst` because its use of the
    # `.. include:: ../README.rst` directive breaks `$ rstcheck`:
    #     CRITICAL:rstcheck_core.checker:An `AttributeError` error occured.
    # Also exclude `./NEWS*.rst` because it's duplicate headings cause:
    #     INFO NEWS.rst:317 Duplicate implicit target name: "bugfixes".
    git ls-files -z '*.rst' ':!docs/index.rst' ':!NEWS*.rst' | xargs -r -0 -- rstcheck

    # Verify Sphinx usage:
    sphinx-build -b "${sphinx_buildername}" -W "./docs/" "./build/docs/"
    sphinx_linkcheck_opts=""
    if test "${GITHUB_ACTIONS:-}" = "true"
    then
	sphinx_linkcheck_opts=" -D linkcheck_ignore=https://liberapay.com/.*"
    fi
    sphinx-build -b "linkcheck" -W ${sphinx_linkcheck_opts} "./docs/" "./build/docs/"
    git ls-files -z '*.rst' | xargs -r -0 -- sphinx-lint -e "all" -d "line-too-long"
    git ls-files -z '*.rst' | xargs -r -0 -- doc8
    git ls-files -z '*.rst' ':!docs/index.rst' ':!NEWS*.rst' |
	xargs -r -0 -- restructuredtext-lint --level "debug"
}


main "$@"
