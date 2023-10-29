# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

# Development, build, and maintenance tasks:
#
# To ease discovery for contributors, place option variables affecting behavior at the
# top. Skip down to `## Top-level targets:` to find targets intended for use by
# developers. The recipes for real targets that follow the top-level targets do the real
# work. If making changes here, start by reading the philosophy commentary at the bottom
# of this file.

# Project specific values:
export PROJECT_NAMESPACE=rpatterson
export PROJECT_NAME=project-structure
# TEMPLATE: Create an Node Package Manager (NPM) organization and set its name here:
NPM_SCOPE=rpattersonnet

# Option variables that control behavior:
export TEMPLATE_IGNORE_EXISTING=false
# https://devguide.python.org/versions/#supported-versions
PYTHON_SUPPORTED_MINORS=3.11 3.12 3.10 3.9 3.8


### "Private" Variables:

# Variables not of concern those running and reading top-level targets. These variables
# most often derive from the environment or other values. Place variables holding
# literal constants or option variables intended for use on the command-line towards the
# top. Otherwise, add variables to the appropriate following grouping. Make requires
# defining variables referenced in targets or prerequisites before those references, in
# contrast with references in recipes. As a result, the Makefile can't place these
# further down for readability and discover.

# Defensive settings for make:
#     https://tech.davis-hansson.com/p/make/
SHELL:=bash
.ONESHELL:
.SHELLFLAGS:=-eu -o pipefail -c
.SILENT:
.DELETE_ON_ERROR:
MAKEFLAGS+=--warn-undefined-variables
MAKEFLAGS+=--no-builtin-rules
PS1?=$$
EMPTY=
COMMA=,

# Values used to install host operating system packages:
HOST_PREFIX=/usr
HOST_PKG_CMD_PREFIX=sudo
HOST_PKG_BIN=apt-get
HOST_PKG_INSTALL_ARGS=install -y
HOST_PKG_NAMES_ENVSUBST=gettext-base
HOST_PKG_NAMES_PIP=python3-pip
HOST_PKG_NAMES_DOCKER=docker-ce-cli docker-compose-plugin
ifneq ($(shell which "brew"),)
HOST_PREFIX=/usr/local
HOST_PKG_CMD_PREFIX=
HOST_PKG_BIN=brew
HOST_PKG_INSTALL_ARGS=install
HOST_PKG_NAMES_ENVSUBST=gettext
HOST_PKG_NAMES_PIP=python
HOST_PKG_NAMES_DOCKER=docker docker-compose
else ifneq ($(shell which "apk"),)
HOST_PKG_BIN=apk
HOST_PKG_INSTALL_ARGS=add
HOST_PKG_NAMES_ENVSUBST=gettext
HOST_PKG_NAMES_PIP=py3-pip
HOST_PKG_NAMES_DOCKER=docker-cli docker-cli-compose
endif
HOST_PKG_CMD=$(HOST_PKG_CMD_PREFIX) $(HOST_PKG_BIN)

# Values derived from the environment:
USER_NAME:=$(shell id -u -n)
USER_FULL_NAME:=$(shell \
    getent passwd "$(USER_NAME)" | cut -d ":" -f 5 | cut -d "," -f 1)
ifeq ($(USER_FULL_NAME),)
USER_FULL_NAME=$(USER_NAME)
endif
USER_EMAIL:=$(USER_NAME)@$(shell hostname -f)
export CHECKOUT_DIR=$(PWD)
# Managed user-specific directory out of the checkout:
# https://specifications.freedesktop.org/basedir-spec/0.8/ar01s03.html
STATE_DIR=$(HOME)/.local/state/$(PROJECT_NAME)

# Values related to supported Python versions:
# Use the same Python version tox would as a default.
# https://tox.wiki/en/latest/config.html#base_python
PYTHON_HOST_MINOR:=$(shell \
    pip3 --version | sed -nE 's|.* \(python ([0-9]+.[0-9]+)\)$$|\1|p;q')
export PYTHON_HOST_ENV=py$(subst .,,$(PYTHON_HOST_MINOR))
# Find the latest installed Python version of the supported versions:
PYTHON_BASENAMES=$(PYTHON_SUPPORTED_MINORS:%=python%)
PYTHON_AVAIL_EXECS:=$(foreach \
    PYTHON_BASENAME,$(PYTHON_BASENAMES),$(shell which $(PYTHON_BASENAME)))
PYTHON_LATEST_EXEC=$(firstword $(PYTHON_AVAIL_EXECS))
PYTHON_LATEST_BASENAME=$(notdir $(PYTHON_LATEST_EXEC))
PYTHON_MINOR=$(PYTHON_HOST_MINOR)
ifeq ($(PYTHON_MINOR),)
# Fallback to the latest installed supported Python version
PYTHON_MINOR=$(PYTHON_LATEST_BASENAME:python%=%)
endif
PYTHON_DEFAULT_MINOR=$(firstword $(PYTHON_SUPPORTED_MINORS))
PYTHON_DEFAULT_ENV=py$(subst .,,$(PYTHON_DEFAULT_MINOR))
PYTHON_MINORS=$(PYTHON_SUPPORTED_MINORS)
ifeq ($(PYTHON_MINOR),)
PYTHON_MINOR=$(firstword $(PYTHON_MINORS))
else ifeq ($(findstring $(PYTHON_MINOR),$(PYTHON_MINORS)),)
PYTHON_MINOR=$(firstword $(PYTHON_MINORS))
endif
export PYTHON_ENV=py$(subst .,,$(PYTHON_MINOR))
PYTHON_SHORT_MINORS=$(subst .,,$(PYTHON_MINORS))
PYTHON_ENVS=$(PYTHON_SHORT_MINORS:%=py%)
PYTHON_ALL_ENVS=$(PYTHON_ENVS) build
PYTHON_EXTRAS=test devel
PYTHON_PROJECT_PACKAGE=$(subst -,,$(PROJECT_NAME))
PYTHON_PROJECT_GLOB=$(subst -,?,$(PROJECT_NAME))

# Values derived from Version Control Systems (VCS):
VCS_LOCAL_BRANCH:=$(shell git branch --show-current)
VCS_TAG=
ifeq ($(VCS_LOCAL_BRANCH),)
# Guess branch name from tag:
ifneq ($(shell echo "$(VCS_TAG)" | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$$'),)
# Publish final releases from the `main` branch:
VCS_LOCAL_BRANCH=main
else ifneq ($(shell echo "$(VCS_TAG)" | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+.+$$'),)
# Publish pre-releases from the `develop` branch:
VCS_LOCAL_BRANCH=develop
endif
endif
# Reproduce Git branch and remote configuration and logic:
VCS_CLONE_REMOTE:=$(shell git config "clone.defaultRemoteName")
ifeq ($(VCS_CLONE_REMOTE),)
VCS_CLONE_REMOTE=origin
endif
VCS_PUSH_REMOTE:=$(shell git config "branch.$(VCS_LOCAL_BRANCH).pushRemote")
ifeq ($(VCS_PUSH_REMOTE),)
VCS_PUSH_REMOTE:=$(shell git config "remote.pushDefault")
endif
ifeq ($(VCS_PUSH_REMOTE),)
VCS_PUSH_REMOTE=$(VCS_CLONE_REMOTE)
endif
VCS_UPSTREAM_REMOTE:=$(shell git config "branch.$(VCS_LOCAL_BRANCH).remote")
ifeq ($(VCS_UPSTREAM_REMOTE),)
VCS_UPSTREAM_REMOTE:=$(shell git config "checkout.defaultRemote")
endif
VCS_UPSTREAM_REF:=$(shell git config "branch.$(VCS_LOCAL_BRANCH).merge")
VCS_UPSTREAM_BRANCH=$(VCS_UPSTREAM_REF:refs/heads/%=%)
# Find the remote and branch for `v*` tags versioning data:
VCS_REMOTE=$(VCS_PUSH_REMOTE)
VCS_BRANCH=$(VCS_LOCAL_BRANCH)
# Find the remote and branch for conventional commits release data:
VCS_COMPARE_REMOTE=$(VCS_UPSTREAM_REMOTE)
ifeq ($(VCS_COMPARE_REMOTE),)
VCS_COMPARE_REMOTE=$(VCS_PUSH_REMOTE)
endif
VCS_COMPARE_BRANCH=$(VCS_UPSTREAM_BRANCH)
ifeq ($(VCS_COMPARE_BRANCH),)
VCS_COMPARE_BRANCH=$(VCS_BRANCH)
endif
# If pushing to upstream release branches, get release data compared to the preceding
# release:
ifeq ($(VCS_COMPARE_BRANCH),develop)
VCS_COMPARE_BRANCH=main
endif
VCS_BRANCH_SUFFIX=upgrade
VCS_MERGE_BRANCH=$(VCS_BRANCH:%-$(VCS_BRANCH_SUFFIX)=%)
# Tolerate detached `HEAD`, such as during a rebase:
VCS_FETCH_TARGETS=
ifneq ($(VCS_BRANCH),)
# Assemble the targets used to avoid redundant fetches during release tasks:
VCS_FETCH_TARGETS+=./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH)
ifneq ($(VCS_REMOTE)/$(VCS_BRANCH),$(VCS_COMPARE_REMOTE)/$(VCS_COMPARE_BRANCH))
VCS_FETCH_TARGETS+=./var/git/refs/remotes/$(VCS_COMPARE_REMOTE)/$(VCS_COMPARE_BRANCH)
endif
# Also fetch develop for merging back in the final release:
VCS_RELEASE_FETCH_TARGETS=./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH)
ifeq ($(VCS_BRANCH),main)
VCS_RELEASE_FETCH_TARGETS+=./var/git/refs/remotes/$(VCS_COMPARE_REMOTE)/develop
ifneq ($(VCS_REMOTE)/$(VCS_BRANCH),$(VCS_COMPARE_REMOTE)/develop)
ifneq ($(VCS_COMPARE_REMOTE)/$(VCS_COMPARE_BRANCH),$(VCS_COMPARE_REMOTE)/develop)
VCS_FETCH_TARGETS+=./var/git/refs/remotes/$(VCS_COMPARE_REMOTE)/develop
endif
endif
endif
ifneq ($(VCS_MERGE_BRANCH),$(VCS_BRANCH))
VCS_FETCH_TARGETS+=./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_MERGE_BRANCH)
endif
endif

# Run Python tools in isolated environments managed by Tox:
# Values used to run Tox:
TOX_ENV_LIST=$(subst $(EMPTY) ,$(COMMA),$(PYTHON_ENVS))
TOX_RUN_ARGS=run-parallel --parallel auto --parallel-live
ifeq ($(words $(PYTHON_MINORS)),1)
TOX_RUN_ARGS=run
endif
# The options that support running arbitrary commands in the venvs managed by tox
# without Tox's startup time:
TOX_EXEC_OPTS=--no-recreate-pkg --skip-pkg-install
TOX_EXEC_ARGS=tox exec $(TOX_EXEC_OPTS) -e "$(PYTHON_DEFAULT_ENV)"
TOX_EXEC_BUILD_ARGS=tox exec $(TOX_EXEC_OPTS) -e "build"
PIP_COMPILE_EXTRA=

# Values used for publishing releases:
# Safe defaults for testing the release process without publishing to the official
# project hosting services, indexes, and registries:
export PIP_COMPILE_ARGS=
RELEASE_PUBLISH=false
PYPI_REPO=testpypi
# Publish releases from the `main` or `develop` branches:
ifeq ($(VCS_BRANCH),main)
RELEASE_PUBLISH=true
else ifeq ($(VCS_BRANCH),develop)
# Publish pre-releases from the `develop` branch:
RELEASE_PUBLISH=true
endif
ifeq ($(RELEASE_PUBLISH),true)
PYPI_REPO=pypi
endif
# Avoid undefined variables warnings when running under local development:
PYPI_PASSWORD=
export PYPI_PASSWORD
TEST_PYPI_PASSWORD=
export TEST_PYPI_PASSWORD

# Override variable values if present in `./.env` and if not overridden on the
# command-line:
include $(wildcard .env)

# Finished with `$(shell)`, echo recipe commands going forward
.SHELLFLAGS+= -x

# <!--alex disable hooks-->


### Top-level targets:

.PHONY: all
## The default target.
all: build


### Build Targets:
#
# Recipes that make artifacts needed for by end-users, development tasks, other recipes.

.PHONY: build
## Perform any necessary local setup common to most operations.
build: ./.git/hooks/pre-commit ./.env.~out~ $(HOST_PREFIX)/bin/docker \
		$(HOME)/.local/bin/tox ./var/log/npm-install.log \
		$(PYTHON_ENVS:%=./.tox/%/bin/pip-compile)
	$(MAKE) -e -j $(PYTHON_ENVS:%=build-requirements-%)

.PHONY: $(PYTHON_ENVS:%=build-requirements-%)
## Compile fixed/pinned dependency versions if necessary.
$(PYTHON_ENVS:%=build-requirements-%):
# Avoid parallel tox recreations stomping on each other
	$(MAKE) -e "$(@:build-requirements-%=./.tox/%/bin/pip-compile)"
	targets="./requirements/$(@:build-requirements-%=%)/user.txt \
	    $(PYTHON_EXTRAS:%=./requirements/$(@:build-requirements-%=%)/%.txt) \
	    ./requirements/$(@:build-requirements-%=%)/build.txt"
# Workaround race conditions in pip's HTTP file cache:
# https://github.com/pypa/pip/issues/6970#issuecomment-527678672
	$(MAKE) -e -j $${targets} ||
	    $(MAKE) -e -j $${targets} ||
	    $(MAKE) -e -j $${targets}

.PHONY: build-requirements-compile
## Compile the requirements for one Python version and one type/extra.
build-requirements-compile:
	$(MAKE) -e "./.tox/$(PYTHON_ENV)/bin/pip-compile"
	pip_compile_opts="--resolver backtracking --strip-extras $(PIP_COMPILE_ARGS)"
ifneq ($(PIP_COMPILE_EXTRA),)
	pip_compile_opts+=" --extra $(PIP_COMPILE_EXTRA)"
endif
	./.tox/$(PYTHON_ENV)/bin/pip-compile $${pip_compile_opts} \
	    --output-file "$(PIP_COMPILE_OUT)" "$(PIP_COMPILE_SRC)"

.PHONY: build-pkgs
## Update the built package for use outside tox.
build-pkgs: $(HOME)/.local/bin/tox ./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH)
# Defined as a .PHONY recipe so that more than one target can depend on this as a
# pre-requisite and it runs one time:
	rm -vf ./dist/*
	tox run -e "$(PYTHON_ENV)" --pkg-only
# Copy the wheel to a location not managed by tox:
	cp -lfv "$$(ls -t ./.tox/.pkg/dist/*.whl | head -n 1)" "./dist/"
# Also build the source distribution:
	tox run -e "$(PYTHON_ENV)" --override "testenv.package=sdist" --pkg-only
	cp -lfv "$$(ls -t ./.tox/.pkg/dist/*.tar.gz | head -n 1)" "./dist/"

.PHONY: build-docs
## Render the static HTML form of the Sphinx documentation
build-docs: build-docs-html

.PHONY: build-docs-watch
## Serve the Sphinx documentation with live updates
build-docs-watch: $(HOME)/.local/bin/tox
	mkdir -pv "./build/docs/html/"
	tox exec -e "build" -- sphinx-autobuild -b "html" "./docs/" "./build/docs/html/"

.PHONY: build-docs-%
# Render the documentation into a specific format.
build-docs-%: $(HOME)/.local/bin/tox
	tox exec -e "build" -- sphinx-build -b "$(@:build-docs-%=%)" -W \
	    "./docs/" "./build/docs/"

.PHONY: build-date
# A prerequisite that always triggers it's target.
build-date:
	date


### Test Targets:
#
# Recipes that run the test suite.

.PHONY: test
## Run the full suite of tests, coverage checks, and linters.
test: $(HOME)/.local/bin/tox test-lint $(PYTHON_ENVS:%=build-requirements-%)
	tox $(TOX_RUN_ARGS) -e "$(TOX_ENV_LIST)"

.PHONY: test-lint
## Perform any linter or style checks, including non-code checks.
test-lint: $(HOST_PREFIX)/bin/docker test-lint-code test-lint-docs test-lint-prose
# Lint copyright and licensing:
	docker compose run --rm -T "reuse"

.PHONY: test-lint-code
## Lint source code for errors, style, and other issues.
test-lint-code: ./var/log/npm-install.log
# Run linters implemented in JavaScript:
	~/.nvm/nvm-exec npm run lint:code

.PHONY: test-lint-docs
## Lint documentation for errors, broken links, and other issues.
test-lint-docs: $(HOME)/.local/bin/tox ./requirements/$(PYTHON_HOST_ENV)/build.txt
# Run linters implemented in Python:
	tox -e build -x 'testenv:build.commands=bin/test-lint-docs.sh'

.PHONY: test-lint-prose
## Lint prose text for spelling, grammar, and style
test-lint-prose: $(HOST_PREFIX)/bin/docker $(HOME)/.local/bin/tox \
		./requirements/$(PYTHON_HOST_ENV)/build.txt ./var/log/npm-install.log
# Lint all markup files tracked in VCS with Vale:
# https://vale.sh/docs/topics/scoping/#formats
	git ls-files -co --exclude-standard -z \
	    ':!NEWS*.rst' ':!LICENSES' ':!styles/Vocab/*.txt' ':!requirements/**' |
	    xargs -r -0 -t -- docker compose run --rm -T vale
# Lint all source code files tracked in VCS with Vale:
	git ls-files -co --exclude-standard -z \
	    ':!styles/*/meta.json' ':!styles/*/*.yml' |
	    xargs -r -0 -t -- \
	    docker compose run --rm -T vale --config="./styles/code.ini"
# Lint source code files tracked in VCS but without extensions with Vale:
	git ls-files -co --exclude-standard -z | grep -Ez '^[^.]+$$' |
	    while read -d $$'\0'
	    do
	        cat "$${REPLY}" |
	            docker compose run --rm -T vale --config="./styles/code.ini" \
	                --ext=".pl"
	    done
# Run linters implemented in Python:
	tox -e build -x 'testenv:build.commands=bin/test-lint-prose.sh'
# Run linters implemented in JavaScript:
	~/.nvm/nvm-exec npm run lint:prose

.PHONY: test-debug
## Run tests directly on the system and start the debugger on errors or failures.
test-debug: $(HOME)/.local/bin/tox ./.tox/$(PYTHON_ENV)/log/editable.log
	$(TOX_EXEC_ARGS) -- pytest --pdb

.PHONY: test-push
## Verify commits before pushing to the remote.
test-push: $(VCS_FETCH_TARGETS) $(HOME)/.local/bin/tox
	vcs_compare_rev="$(VCS_COMPARE_REMOTE)/$(VCS_COMPARE_BRANCH)"
	if ! git fetch "$(VCS_COMPARE_REMOTE)" "$(VCS_COMPARE_BRANCH)"
	then
# For a newly created branch not yet on the remote, compare with the pre-release branch:
	    vcs_compare_rev="$(VCS_COMPARE_REMOTE)/develop"
	fi
	exit_code=0
	(
	    $(TOX_EXEC_BUILD_ARGS) -- \
	        cz check --rev-range "$${vcs_compare_rev}..HEAD" &&
	    $(TOX_EXEC_BUILD_ARGS) -- \
	        python ./bin/cz-check-bump.py --compare-ref "$${vcs_compare_rev}"
	) || exit_code=$$?
	if (( $$exit_code == 3 || $$exit_code == 21 ))
	then
	    exit
	elif (( $$exit_code != 0 ))
	then
	    exit $$exit_code
	else
	    $(TOX_EXEC_BUILD_ARGS) -- \
	        towncrier check --compare-with "$${vcs_compare_rev}"
	fi

.PHONY: test-clean
## Confirm that the checkout has no uncommitted VCS changes.
test-clean:
	if test -n "$$(git status --porcelain)"
	then
	    git status -vv
	    set +x
	    echo "WARNING: Checkout is not clean."
	    false
	fi


### Release Targets:
#
# Recipes that make an changes needed for releases and publish built artifacts to
# end-users.

.PHONY: release
release: $(HOME)/.local/bin/tox ~/.pypirc.~out~
## Publish PyPI packages and Docker images if conventional commits require a release.
# Don't release unless from the `main` or `develop` branches:
ifeq ($(RELEASE_PUBLISH),true)
	$(MAKE) -e build-pkgs
# https://twine.readthedocs.io/en/latest/#using-twine
	$(TOX_EXEC_BUILD_ARGS) -- twine check ./dist/$(PYTHON_PROJECT_GLOB)-*
# Ensure VCS has captured all the effects of building the release:
	$(MAKE) -e test-clean
	$(TOX_EXEC_BUILD_ARGS) -- twine upload -s -r "$(PYPI_REPO)" \
	    ./dist/$(PYTHON_PROJECT_GLOB)-*
endif

.PHONY: release-bump
## Bump the package version if conventional commits require a release.
release-bump: $(VCS_RELEASE_FETCH_TARGETS) $(HOME)/.local/bin/tox \
		./var/log/npm-install.log
	if ! git diff --cached --exit-code
	then
	    set +x
	    echo "CRITICAL: Cannot bump version with staged changes"
	    false
	fi
# Update the local branch to the forthcoming version bump commit:
	git switch -C "$(VCS_BRANCH)" "$$(git rev-parse HEAD)"
	exit_code=0
	if test "$(VCS_BRANCH)" = "main" &&
	    $(TOX_EXEC_BUILD_ARGS) -- python ./bin/get-base-version.py $$(
	        $(TOX_EXEC_BUILD_ARGS) -qq -- cz version --project
	    )
	then
# Make a final release from the last pre-release:
	    true
	else
# Do the conventional commits require a release?:
	    $(TOX_EXEC_BUILD_ARGS) -- python ./bin/cz-check-bump.py || exit_code=$$?
	    if (( $$exit_code == 3 || $$exit_code == 21 ))
	    then
# No commits require a release:
	        exit
	    elif (( $$exit_code != 0 ))
	    then
	        exit $$exit_code
	    fi
	fi
# Collect the versions involved in this release according to conventional commits:
	cz_bump_args="--check-consistency --no-verify"
ifneq ($(VCS_BRANCH),main)
	cz_bump_args+=" --prerelease beta"
endif
# Build and stage the release notes:
	next_version=$$(
	    $(TOX_EXEC_BUILD_ARGS) -qq -- cz bump $${cz_bump_args} --yes --dry-run |
	    sed -nE 's|.* ([^ ]+) *→ *([^ ]+).*|\2|p;q'
	) || true
# Assemble the release notes for this next version:
	$(TOX_EXEC_BUILD_ARGS) -qq -- \
	    towncrier build --version "$${next_version}" --draft --yes \
	    >"./NEWS-VERSION.rst"
	git add -- "./NEWS-VERSION.rst"
	$(TOX_EXEC_BUILD_ARGS) -- towncrier build --version "$${next_version}" --yes
# Bump the version in the NPM package metadata:
	~/.nvm/nvm-exec npm --no-git-tag-version version "$${next_version}"
	git add -- "./package*.json"
# Increment the version in VCS
	$(TOX_EXEC_BUILD_ARGS) -- cz bump $${cz_bump_args}
ifeq ($(VCS_BRANCH),main)
# Merge the bumped version back into `develop`:
	$(MAKE) VCS_BRANCH="main" VCS_MERGE_BRANCH="develop" \
	    VCS_REMOTE="$(VCS_COMPARE_REMOTE)" VCS_MERGE_BRANCH="develop" devel-merge
	git switch -C "$(VCS_BRANCH)" "$$(git rev-parse HEAD)"
endif


### Development Targets:
#
# Recipes used by developers to make changes to the code.

.PHONY: devel-format
## Automatically correct code in this checkout according to linters and style checkers.
devel-format: $(HOST_PREFIX)/bin/docker ./var/log/npm-install.log $(HOME)/.local/bin/tox
# Add license and copyright header to files missing them:
	git ls-files -co --exclude-standard -z ':!*.license' ':!.reuse' ':!LICENSES' \
	    ':!newsfragments/*' ':!NEWS*.rst' ':!styles/*/meta.json' \
	    ':!styles/*/*.yml' ':!requirements/*/*.txt' |
	while read -d $$'\0'
	do
	    if ! (
	        test -e  "$${REPLY}.license" ||
	        grep -Eq 'SPDX-License-Identifier:' "$${REPLY}"
	    )
	    then
	        echo "$${REPLY}"
	    fi
	done | xargs -r -t -- \
	    docker compose run --rm -T "reuse" annotate --skip-unrecognised \
	        --copyright "Ross Patterson <me@rpatterson.net>" --license "MIT"
# Run source code formatting tools implemented in JavaScript:
	~/.nvm/nvm-exec npm run format
# Run source code formatting tools implemented in Python:
	$(TOX_EXEC_ARGS) -- autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables "./src/$(PYTHON_PROJECT_PACKAGE)/"
	$(TOX_EXEC_ARGS) -- autopep8 -v -i -r "./src/$(PYTHON_PROJECT_PACKAGE)/"
	$(TOX_EXEC_ARGS) -- black "./src/$(PYTHON_PROJECT_PACKAGE)/"

.PHONY: devel-upgrade
## Update all locked or frozen dependencies to their most recent available versions.
devel-upgrade: $(HOME)/.local/bin/tox $(PYTHON_ENVS:%=./.tox/%/bin/pip-compile)
	touch "./setup.cfg" "./requirements/build.txt.in"
	$(MAKE) -e -j  PIP_COMPILE_ARGS="--upgrade" \
	    $(PYTHON_ENVS:%=build-requirements-%)
# Update VCS integration from remotes to the most recent tag:
	$(TOX_EXEC_BUILD_ARGS) -- pre-commit autoupdate
# Update the Vale style rule definitions:
	touch "./.vale.ini" "./styles/code.ini"
	$(MAKE) "./var/log/vale-rule-levels.log"

.PHONY: devel-upgrade-branch
## Reset an upgrade branch, commit upgraded dependencies on it, and push for review.
devel-upgrade-branch: ./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH)
	if ! $(MAKE) -e "test-clean"
	then
	    set +x
	    echo "ERROR: Can't upgrade with uncommitted changes."
	    exit 1
	fi
	now=$$(date -u)
	$(MAKE) -e TEMPLATE_IGNORE_EXISTING="true" devel-upgrade
	if $(MAKE) -e "test-clean"
	then
# No changes from upgrade, exit signaling success but push nothing:
	    exit
	fi
	git switch -C "$(VCS_BRANCH)-upgrade"
# Only add changes upgrade-related changes:
	git add --update './requirements/*/*.txt' "./.pre-commit-config.yaml" \
	    "./.vale.ini" "./styles/"
# Commit the upgrade changes
	echo "Upgrade all requirements to the most recent versions as of" \
	    >"./newsfragments/+upgrade-requirements.bugfix.rst"
	echo "$${now}." >>"./newsfragments/+upgrade-requirements.bugfix.rst"
	git add "./newsfragments/+upgrade-requirements.bugfix.rst"
	git commit --all --gpg-sign -m \
	    "fix(deps): Upgrade to most recent versions"
# Fail if upgrading left un-tracked files in VCS:
	$(MAKE) -e "test-clean"

.PHONY: devel-merge
## Merge this branch with a suffix back into its un-suffixed upstream.
devel-merge: ./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_MERGE_BRANCH)
	merge_rev="$$(git rev-parse HEAD)"
	git switch -C "$(VCS_MERGE_BRANCH)" --track "$(VCS_REMOTE)/$(VCS_MERGE_BRANCH)"
	git merge --ff --gpg-sign -m \
	    $$'Merge branch \'$(VCS_BRANCH)\' into $(VCS_MERGE_BRANCH)\n\n[ci merge]' \
	    "$${merge_rev}"


### Clean Targets:
#
# Recipes used to restore the checkout to initial conditions.

.PHONY: clean
## Restore the checkout to an initial clone state.
clean:
	$(TOX_EXEC_BUILD_ARGS) -- pre-commit uninstall \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push" \
	    || true
	$(TOX_EXEC_BUILD_ARGS) -- pre-commit clean || true
	git clean -dfx -e "/var" -e "/.env" -e "*~"
	rm -rfv "./var/log/"


### Real Targets:
#
# Recipes that make actual changes and create and update files for the target.

# Manage fixed/pinned versions in `./requirements/**.txt` files. Must run for each
# python version in the virtual environment for that Python version:
# https://github.com/jazzband/pip-tools#cross-environment-usage-of-requirementsinrequirementstxt-and-pip-compile
python_combine_requirements=$(PYTHON_ENVS:%=./requirements/%/$(1).txt)
$(foreach extra,$(PYTHON_EXTRAS),$(call python_combine_requirements,$(extra))): \
		./pyproject.toml ./setup.cfg ./tox.ini
	true DEBUG Updated prereqs: $(?)
	extra_basename="$$(basename "$(@)")"
	$(MAKE) -e PYTHON_ENV="$$(basename "$$(dirname "$(@)")")" \
	    PIP_COMPILE_EXTRA="$${extra_basename%.txt}" \
	    PIP_COMPILE_SRC="$(<)" PIP_COMPILE_OUT="$(@)" \
	    build-requirements-compile
$(PYTHON_ENVS:%=./requirements/%/user.txt): ./pyproject.toml ./setup.cfg ./tox.ini
	true DEBUG Updated prereqs: $(?)
	$(MAKE) -e PYTHON_ENV="$(@:requirements/%/user.txt=%)" PIP_COMPILE_SRC="$(<)" \
	    PIP_COMPILE_OUT="$(@)" build-requirements-compile
$(PYTHON_ENVS:%=./requirements/%/build.txt): ./requirements/build.txt.in
	true DEBUG Updated prereqs: $(?)
	$(MAKE) -e PYTHON_ENV="$(@:requirements/%/build.txt=%)" PIP_COMPILE_SRC="$(<)" \
	    PIP_COMPILE_OUT="$(@)" build-requirements-compile

# Capture any project initialization tasks for reference. Not actually usable.
./pyproject.toml:
	$(MAKE) -e "$(HOME)/.local/bin/tox"
	$(TOX_EXEC_BUILD_ARGS) -- cz init

# Local environment variables and secrets from a template:
./.env.~out~: ./.env.in
	$(call expand_template,$(<),$(@))

./README.md: README.rst
	$(MAKE) "$(HOST_PREFIX)/bin/docker"
	docker compose run --rm "pandoc"


### Development Tools:

# VCS configuration and integration:
# Retrieve VCS data needed for versioning, tags, and releases, release notes:
$(VCS_FETCH_TARGETS): ./.git/logs/HEAD
	git_fetch_args="--tags --prune --prune-tags --force"
	if test "$$(git rev-parse --is-shallow-repository)" = "true"
	then
	    git_fetch_args+=" --unshallow"
	fi
	branch_path="$(@:var/git/refs/remotes/%=%)"
	mkdir -pv "$(dir $(@))"
	if ! git fetch $${git_fetch_args} "$${branch_path%%/*}" "$${branch_path#*/}" |&
	    tee -a "$(@)"
	then
# If the local branch doesn't exist, fall back to the pre-release branch:
	    git fetch $${git_fetch_args} "$${branch_path%%/*}" "develop" |&
	        tee -a "$(@)"
	fi
# A target whose `mtime` reflects files added to or removed from VCS:
./var/log/git-ls-files.log: build-date
	mkdir -pv "$(dir $(@))"
	git ls-files >"$(@).~new~"
	if diff -u "$(@)" "$(@).~new~"
	then
	    exit
	fi
	mv -v "$(@).~new~" "$(@)"
./.git/hooks/pre-commit:
	$(MAKE) -e "$(HOME)/.local/bin/tox"
	$(TOX_EXEC_BUILD_ARGS) -- pre-commit install \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push"

# Prose linting:
# Map formats unknown by Vale to a common default format:
./var/log/vale-map-formats.log: ./bin/vale-map-formats.py ./.vale.ini \
		./var/log/git-ls-files.log
	$(MAKE) -e "$(HOME)/.local/bin/tox"
	$(TOX_EXEC_BUILD_ARGS) -- python "$(<)" "./styles/code.ini" "./.vale.ini"
# Set Vale levels for added style rules:
# Must be it's own target because Vale sync takes the sets of styles from the
# configuration and the configuration needs the styles to set rule levels:
./var/log/vale-rule-levels.log: ./styles/RedHat/meta.json
	$(MAKE) -e "$(HOME)/.local/bin/tox"
	$(TOX_EXEC_BUILD_ARGS) -- python ./bin/vale-set-rule-levels.py
	$(TOX_EXEC_BUILD_ARGS) -- python ./bin/vale-set-rule-levels.py \
	    --input="./styles/code.ini"
# Update style rule definitions from the remotes:
./styles/RedHat/meta.json: ./.vale.ini ./styles/code.ini ./.env.~out~
	$(MAKE) "$(HOST_PREFIX)/bin/docker"
	docker compose run --rm vale sync
	docker compose run --rm -T vale sync --config="./styles/code.ini"

# Editor and IDE support and integration:
./.dir-locals.el.~out~: ./.dir-locals.el.in
	$(call expand_template,$(<),$(@))

# Manage JavaScript tools:
./var/log/npm-install.log: ./package.json ./var/log/nvm-install.log
	mkdir -pv "$(dir $(@))"
	~/.nvm/nvm-exec npm install | tee -a "$(@)"
./package.json:
	$(MAKE) "./var/log/nvm-install.log"
# https://docs.npmjs.com/creating-a-package-json-file#creating-a-default-packagejson-file
	~/.nvm/nvm-exec npm init --yes --scope="@$(NPM_SCOPE)"
./var/log/nvm-install.log: ./.nvmrc
	$(MAKE) "$(HOME)/.nvm/nvm.sh"
	mkdir -pv "$(dir $(@))"
	set +x
	. "$(HOME)/.nvm/nvm.sh" || true
	nvm install | tee -a "$(@)"
# https://github.com/nvm-sh/nvm#install--update-script
$(HOME)/.nvm/nvm.sh:
	set +x
	wget -qO- "https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.3/install.sh"
	    | bash

# Manage Python tools:
# Targets used as pre-requisites to ensure virtual environments managed by tox have been
# created so other targets can use them directly to save Tox's startup time when they
# don't need Tox's logic about when to update/recreate them, e.g.:
#     $ ./.tox/build/bin/cz --help
# Useful for build/release tools:
$(PYTHON_ALL_ENVS:%=./.tox/%/bin/pip-compile):
	$(MAKE) -e "$(HOME)/.local/bin/tox"
	tox run $(TOX_EXEC_OPTS) -e "$(@:.tox/%/bin/pip-compile=%)" --notest
# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`. Use as a
# prerequisite for targets that use Tox virtual environments directly and changes to
# code need to take effect in real-time:
$(PYTHON_ENVS:%=./.tox/%/log/editable.log):
	$(MAKE) -e "$(HOME)/.local/bin/tox"
	mkdir -pv "$(dir $(@))"
	tox exec $(TOX_EXEC_OPTS) -e "$(@:.tox/%/log/editable.log=%)" -- \
	    pip3 install -e "./" |& tee -a "$(@)"
$(HOME)/.local/bin/tox:
	$(MAKE) "$(HOME)/.local/bin/pipx"
# https://tox.wiki/en/latest/installation.html#via-pipx
	pipx install "tox"
$(HOME)/.local/bin/pipx:
	$(MAKE) "$(HOST_PREFIX)/bin/pip3"
# https://pypa.github.io/pipx/installation/#install-pipx
	pip3 install --user "pipx"
	python3 -m pipx ensurepath
$(HOST_PREFIX)/bin/pip3:
	$(MAKE) "$(STATE_DIR)/log/host-update.log"
	$(HOST_PKG_CMD) $(HOST_PKG_INSTALL_ARGS) "$(HOST_PKG_NAMES_PIP)"

# Manage tools in containers:
$(HOST_PREFIX)/bin/docker:
	$(MAKE) "$(STATE_DIR)/log/host-update.log"
	$(HOST_PKG_CMD) $(HOST_PKG_INSTALL_ARGS) "$(HOST_PKG_NAMES_DOCKER)"
	docker info
ifeq ($(HOST_PKG_BIN),brew)
# https://formulae.brew.sh/formula/docker-compose#default
	mkdir -p ~/.docker/cli-plugins
	ln -sfnv "$${HOMEBREW_PREFIX}/opt/docker-compose/bin/docker-compose" \
	    "~/.docker/cli-plugins/docker-compose"
endif

# Support for installing host operating system packages:
$(STATE_DIR)/log/host-update.log:
	if ! $(HOST_PKG_CMD_PREFIX) which $(HOST_PKG_BIN)
	then
	    set +x
	    echo "ERROR: OS not supported for installing system dependencies"
	    false
	fi
	$(HOST_PKG_CMD) update | tee -a "$(@)"

# Set up release publishing authentication, useful in automation such as CI:
~/.pypirc.~out~: ./home/.pypirc.in
	$(call expand_template,$(<),$(@))


### Makefile "functions":
#
# Snippets used several times, including in different recipes:
# https://www.gnu.org/software/make/manual/html_node/Call-Function.html

# Return the most recent built package:
current_pkg=$(shell ls -t ./dist/*$(1) | head -n 1)

# Have to use a placeholder `*.~out~` target instead of the real expanded template
# because targets can't disable `.DELETE_ON_ERROR` on a per-target basis.
#
# Can't use a target and recipe to install `$ envsubst`. Shouldn't update expanded
# templates when `/usr/bin/envsubst` changes but expanding a template requires it to be
# installed. The recipe can't use a sub-make because Make updates any expanded template
# targets used in `include` directives when reading the `./Makefile`, for example
# `./.env`, leading to endless recursion:
define expand_template=
if ! which envsubst
then
    $(HOST_PKG_CMD) update | tee -a "$(STATE_DIR)/log/host-update.log"
    $(HOST_PKG_CMD) $(HOST_PKG_INSTALL_ARGS) "$(HOST_PKG_NAMES_ENVSUBST)"
fi
if test "$(2:%.~out~=%)" -nt "$(1)"
then
    envsubst <"$(1)" >"$(2)"
    exit
fi
if test ! -e "$(2:%.~out~=%)"
then
    touch -d "@0" "$(2:%.~out~=%)"
fi
envsubst <"$(1)" | diff -u "$(2:%.~out~=%)" "-" || true
set +x
echo "WARNING:Template $(1) changed, reconcile and \`$$ touch $(2:%.~out~=%)\`."
set -x
if test ! -s "$(2:%.~out~=%)"
then
    envsubst <"$(1)" >"$(2:%.~out~=%)"
    touch -d "@0" "$(2:%.~out~=%)"
fi
if test "$(TEMPLATE_IGNORE_EXISTING)" = "true"
then
    envsubst <"$(1)" >"$(2:%.~out~=%)"
    exit
fi
exit 1
endef


### Makefile Development:
#
# Development primarily requires a balance of 2 priorities:
#
# - Correctness of the source code and build artifacts
# - Reduce iteration time in the inner loop of development
#
# This project uses Make to balance those priorities. Target recipes capture the
# commands necessary to build artifacts, run tests, and verify the code. Top-level
# targets compose related target recipes for often needed tasks. Targets use
# prerequisites to define when to update build artifacts prevent time wasted on
# unnecessary updates in the inner loop of development.
#
# Make provides an important feature to achieve that second priority, a framework for
# determining when to do work. Targets define build artifact paths. The target's recipe
# lists the commands that create or update that build artifact. The target's
# prerequisites define when to update that target. Make runs the recipe when any of the
# prerequisites have more recent modification times than the target to update the
# target.
#
# For example, if a feature adds library to the project's dependencies, correctness
# requires the project to update the frozen, or locked versions to include the added
# library. The rest of the time the locked or frozen versions don't need updating and it
# wastes significant time to always update them in the inner loop of development. To
# express such relationships in Make, define targets for the files containing the locked
# or frozen versions and add a prerequisite for the file that defines dependencies:
#
#    ./build/bar.txt: ./bar.txt.in
#    	envsubst <"$(<)" >"$(@)"
#
# To that end, use real target and prerequisite files whenever possible when adding
# recipes to this file. Make calls targets whose name doesn't correspond to a real build
# artifact `.PHONY:` targets. Use `.PHONY:` targets to compose sets or real targets and
# define recipes for tasks that don't produce build artifacts, for example, the
# top-level targets.

# If a recipe doesn't produce an appropriate build artifact, define an arbitrary target
# the recipe writes to, such as piping output to a log file. Also use this approach when
# none of the modification times of produced artifacts reflect when any downstream
# targets need updating:
#
#     ./var/log/some-work.log:
#         mkdir -pv "$(dir $(@))"
#         ./.tox/build/bin/python "./bin/do-some-work.py" | tee -a "$(@)"
#
# If the recipe produces no output, the recipe can create arbitrary output:
#
#     ./var/log/bar.log:
#         echo "Do some work here"
#         mkdir -pv "$(dir $(@))"
#         date | tee -a "$(@)"
#
# If the recipe of a target needs another target but updating that other target doesn't
# mean that this target's recipe needs to re-run, such as one-time system install tasks,
# use that target in a sub-make instead of a prerequisite:
#
#     ./var/log/bar.log:
#         $(MAKE) "./var/log/qux.log"
#
# This project uses some more Make features than these core features and welcome further
# use of such features:
#
# - `$(@)`:
#   The automatic variable containing the path for the target
#
# - `$(<)`:
#   The automatic variable containing the path for the first prerequisite
#
# - `$(VARIABLE_FOO:%=bar-%)`:
#   Substitution references to generate transformations of space-separated values
#
# - `$ make OPTION_FOO=bar`:
#   Use "option" variables and support overriding on the command-line
#
# Avoid the more "magical" features of Make, to keep it readable, discover-able, and
# otherwise approachable to developers who might not have significant familiarity with
# Make. If you have good, pragmatic reasons to add use of further features, make the
# case for them but avoid them if possible.
