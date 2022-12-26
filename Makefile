## Development, build and maintenance tasks

### Defensive settings for make:
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

# Variables/options that affect behavior
# https://devguide.python.org/versions/#supported-versions
PYTHON_SUPPORTED_MINORS=3.11 3.10 3.9 3.8 3.7

# Values derived from the environment
USER_NAME:=$(shell id -u -n)
USER_FULL_NAME:=$(shell getent passwd "$(USER_NAME)" | cut -d ":" -f 5 | cut -d "," -f 1)
ifeq ($(USER_FULL_NAME),)
USER_FULL_NAME=$(USER_NAME)
endif
USER_EMAIL:=$(USER_NAME)@$(shell hostname --fqdn)
# Use the same Python version tox would as a default:
# https://tox.wiki/en/latest/config.html#base_python
PYTHON_MINOR:=$(shell pip --version | sed -nE 's|.* \(python ([0-9]+.[0-9]+)\)$$|\1|p')
# Determine the latest installed Python version of the supported versions
PYTHON_BASENAMES=$(PYTHON_SUPPORTED_MINORS:%=python%)
define PYTHON_AVAIL_EXECS :=
    $(foreach PYTHON_BASENAME,$(PYTHON_BASENAMES),$(shell which $(PYTHON_BASENAME)))
endef
PYTHON_LATEST_EXEC=$(firstword $(PYTHON_AVAIL_EXECS))
PYTHON_LATEST_BASENAME=$(notdir $(PYTHON_LATEST_EXEC))
ifeq ($(PYTHON_MINOR),)
# Fallback to the latest installed supported Python version
PYTHON_MINOR=$(PYTHON_LATEST_BASENAME:python%=%)
endif

# Values derived from constants
# Support passing in the Python versions to test, including testing one version:
#     $ make PYTHON_MINORS=3.11 test
PYTHON_LATEST_MINOR=$(firstword $(PYTHON_SUPPORTED_MINORS))
PYTHON_LATEST_ENV=py$(subst .,,$(PYTHON_LATEST_MINOR))
PYTHON_MINORS=$(PYTHON_SUPPORTED_MINORS)
ifeq ($(PYTHON_MINOR),)
PYTHON_MINOR=$(firstword $(PYTHON_MINORS))
else ifeq ($(findstring $(PYTHON_MINOR),$(PYTHON_MINORS)),)
PYTHON_MINOR=$(firstword $(PYTHON_MINORS))
endif
export PYTHON_ENV=py$(subst .,,$(PYTHON_MINOR))
PYTHON_SHORT_MINORS=$(subst .,,$(PYTHON_MINORS))
PYTHON_ENVS=$(PYTHON_SHORT_MINORS:%=py%)
TOX_ENV_LIST=$(subst $(EMPTY) ,$(COMMA),$(PYTHON_ENVS))
TOX_RUN_ARGS=run-parallel --parallel auto --parallel-live
ifeq ($(words $(PYTHON_MINORS)),1)
TOX_RUN_ARGS=run
endif

# Safe defaults for testing the release process without publishing to the final/official
# hosts/indexes/registries:
RELEASE_PUBLISH=false
TOWNCRIER_COMPARE_BRANCH=develop
PYPI_REPO=testpypi
# Only publish releases from the `master` or `develop` branches:
VCS_BRANCH:=$(shell git branch --show-current)
ifeq ($(VCS_BRANCH),master)
RELEASE_PUBLISH=true
TOWNCRIER_COMPARE_BRANCH=master
PYPI_REPO=pypi
else ifeq ($(VCS_BRANCH),develop)
# Publish pre-releases from the `develop` branch:
RELEASE_PUBLISH=true
endif

# Done with `$(shell ...)`, echo recipe commands going forward
.SHELLFLAGS+= -x


## Top-level targets

.PHONY: all
### Default target
all: build

.PHONY: build
### Perform any currently necessary local set-up common to most operations
build: \
		./var/log/host-install.log \
		./.git/hooks/pre-commit \
		./.tox/$(PYTHON_ENV)/bin/activate
# Parallelizing all `$ pip-compile` runs seems to fail intermittently with:
#     WARNING: Skipping page https://pypi.org/simple/wheel/ because the GET request got
#     Content-Type: .  The only supported Content-Type is text/html
# I assume it's some sort of PyPI rate limiting.  Remove one or both of the next two `$
# make -j` options if you don't find the trade off worth it.
	$(MAKE) -e -j $(PYTHON_ENVS:%=build-requirements-%)
.PHONY: $(PYTHON_ENVS:%=build-requirements-%)
### Compile fixed/pinned dependency versions if necessary
$(PYTHON_ENVS:%=build-requirements-%):
	$(MAKE) -e -j \
	    "./requirements/$(@:build-requirements-%=%)/user.txt" \
	    "./requirements/$(@:build-requirements-%=%)/devel.txt" \
	    "./requirements/$(@:build-requirements-%=%)/build.txt" \
	    "./requirements/$(@:build-requirements-%=%)/host.txt"
.PHONY: build-bump
### Bump the package version if on a branch that should trigger a release
build-bump: ~/.gitconfig ./.tox/$(PYTHON_ENV)/bin/activate
# Collect the versions involved in this release according to conventional commits
	cz_bump_args="--check-consistency --no-verify"
ifneq ($(VCS_BRANCH),master)
	cz_bump_args+=" --prerelease beta"
endif
# Run first in case any input is needed from the developer
	exit_code=0
	./.tox/build/bin/cz bump $${cz_bump_args} --dry-run || exit_code=$$?
	rm -fv "./.tox/build/cz-bump-no-release.txt"
	if (( $$exit_code == 3 || $$exit_code == 21 ))
	then
# No release necessary for the commits since the last release, don't publish a release
	    echo "true" >"./.tox/build/cz-bump-no-release.txt"
	    exit
	elif (( $$exit_code != 0 ))
	then
# Commitizen returned an unexpected exit status code, fail
	    exit $$exit_code
	fi
	cz_bump_args+=" --yes"
	next_version="$$(
	    ./.tox/build/bin/cz bump $${cz_bump_args} --dry-run |
	    sed -nE 's|.* *[Vv]ersion *(.+) *→ *(.+)|\2|p'
	)"
# Update the release notes/changelog
	git fetch --no-tags origin "$(TOWNCRIER_COMPARE_BRANCH)"
	./.tox/$(PYTHON_ENV)/bin/towncrier check \
	    --compare-with "origin/$(TOWNCRIER_COMPARE_BRANCH)"
	if ! git diff --cached --exit-code
	then
	    set +x
	    echo "CRITICAL: Cannot bump version with staged changes"
	    false
	fi
# Build and stage the release notes to be commited by `$ cz bump`
	./.tox/$(PYTHON_ENV)/bin/towncrier build --version "$${next_version}" --yes
# Increment the version in VCS
	./.tox/build/bin/cz bump $${cz_bump_args}
# Prevent uploading unintended distributions
	rm -vf ./.tox/$(PYTHON_ENV)/dist/* ./.tox/.pkg/dist/*

.PHONY: check-push
### Perform any checks that should only be run before pushing
check-push: ./.tox/$(PYTHON_ENV)/bin/activate
ifeq ($(RELEASE_PUBLISH),true)
	./.tox/$(PYTHON_ENV)/bin/towncrier check --compare-with "origin/develop"
endif

.PHONY: release
### Publish installable Python packages to PyPI
release: ./.tox/$(PYTHON_ENV)/bin/activate ~/.pypirc
# Build the actual release artifacts, tox builds the `sdist` so here we build the wheel
	./.tox/$(PYTHON_ENV)/bin/pyproject-build \
	    --outdir "./.tox/$(PYTHON_ENV)/dist/" -w
# https://twine.readthedocs.io/en/latest/#using-twine
	./.tox/build/bin/twine check ./.tox/$(PYTHON_ENV)/dist/* ./.tox/.pkg/dist/*
	if [ ! -z "$$(git status --porcelain)" ]
	then
	    set +x
	    echo "CRITICAL: Checkout is not clean, not publishing release"
	    false
	fi
	if [ -e "./.tox/build/cz-bump-no-release.txt" ]
	then
	    exit
	fi
ifeq ($(RELEASE_PUBLISH),true)
# Publish from the local host outside a container for access to user credentials:
# https://twine.readthedocs.io/en/latest/#using-twine
# Only release on `master` or `develop` to avoid duplicate uploads
	./.tox/build/bin/twine upload -s -r "$(PYPI_REPO)" \
	    ./.tox/$(PYTHON_ENV)/dist/* ./.tox/.pkg/dist/*
# The VCS remote shouldn't reflect the release until the release has been successfully
# published
	git push --no-verify --tags origin $(VCS_BRANCH)
endif

.PHONY: format
### Automatically correct code in this checkout according to linters and style checkers
format: ./.tox/$(PYTHON_ENV)/bin/activate
	./.tox/$(PYTHON_ENV)/bin/autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables "./src/pythonprojectstructure/"
	./.tox/$(PYTHON_ENV)/bin/autopep8 -v -i -r "./src/pythonprojectstructure/"
	./.tox/$(PYTHON_ENV)/bin/black "./src/pythonprojectstructure/"

.PHONY: test
### Run the full suite of tests, coverage checks, and linters
test: build
	tox $(TOX_RUN_ARGS) -e "$(TOX_ENV_LIST)"

.PHONY: test-debug
### Run tests in the main/default environment and invoke the debugger on errors/failures
test-debug: ./.tox/$(PYTHON_ENV)/log/editable.log
	./.tox/$(PYTHON_ENV)/bin/pytest --pdb

.PHONY: upgrade
### Update all fixed/pinned dependencies to their latest available versions
upgrade:
	touch "./setup.cfg" "./requirements/build.txt.in" "./requirements/host.txt.in"
	$(MAKE) -e "build"
# Update VCS hooks from remotes to the latest tag.
	./.tox/build/bin/pre-commit autoupdate

.PHONY: clean
### Restore the checkout to a state as close to an initial clone as possible
clean:
	./.tox/build/bin/pre-commit uninstall \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push" \
	    || true
	./.tox/build/bin/pre-commit clean || true
	git clean -dfx -e "var/"
	rm -rfv "./var/log/"


## Utility targets

.PHONY: expand-template
## Create a file from a template replacing environment variables
expand-template: .SHELLFLAGS = -eu -o pipefail -c
expand-template: ./var/log/host-install.log
	if [ -e "$(target)" ]
	then
	    diff -u "$(target)" "$(template)" || true
	    echo "ERROR: Template $(template) has been updated:"
	    echo "       Reconcile changes and \`$$ touch $(target)\`:"
	    false
	fi
	envsubst <"$(template)" >"$(target)"


## Real targets

# Manage fixed/pinned versions in `./requirements/**.txt` files.  Has to be run for each
# python version in the virtual environment for that Python version:
# https://github.com/jazzband/pip-tools#cross-environment-usage-of-requirementsinrequirementstxt-and-pip-compile
$(PYTHON_ENVS:%=./requirements/%/devel.txt): \
		./pyproject.toml ./setup.cfg ./tox.ini ./.tox/$(PYTHON_ENV)/bin/activate
	ls -lnt $(?)
	./.tox/$(@:requirements/%/devel.txt=%)/bin/pip-compile \
	    --resolver=backtracking --upgrade --extra="devel" \
	    --output-file="$(@)" "$(<)"
$(PYTHON_ENVS:%=./requirements/%/user.txt): \
		./pyproject.toml ./setup.cfg ./tox.ini ./.tox/$(PYTHON_ENV)/bin/activate
	ls -lnt $(?)
	./.tox/$(@:requirements/%/user.txt=%)/bin/pip-compile \
	    --resolver=backtracking --upgrade --output-file="$(@)" "$(<)"
$(PYTHON_ENVS:%=./requirements/%/host.txt): \
		./requirements/host.txt.in ./.tox/$(PYTHON_ENV)/bin/activate
	ls -lnt $(?)
	./.tox/$(@:requirements/%/host.txt=%)/bin/pip-compile \
	    --resolver=backtracking --upgrade --output-file="$(@)" "$(<)"
	if [ "$(@:requirements/%/host.txt=%)" = "$(PYTHON_ENV)" ]
	then
# Only update the installed tox version for the latest/host/main/default Python version
	    pip install -r "$(@)"
	fi
$(PYTHON_ENVS:%=./requirements/%/build.txt): \
		./requirements/build.txt.in ./.tox/$(PYTHON_ENV)/bin/activate
	ls -lnt $(?)
	./.tox/$(@:requirements/%/build.txt=%)/bin/pip-compile \
	    --resolver=backtracking --upgrade --output-file="$(@)" "$(<)"

# Use any Python version target to represent building all versions.
./.tox/$(PYTHON_ENV)/bin/activate: ./var/log/host-install.log
	ls -lnt $(?)
# Bootstrap frozen/pinned versions if necessary
	if [ ! -e "./requirements/$(PYTHON_ENV)/build.txt" ]
	then
	    cp -av "./requirements/build.txt.in" \
	        "./requirements/$(PYTHON_ENV)/build.txt"
# Ensure frozen/pinned versions will subsequently be compiled
	    touch "./requirements/build.txt.in"
	fi
	for reqs in $(PYTHON_ENVS:%=./requirements/%/devel.txt)
	do
	    if [ ! -e "$${reqs}" ]
	    then
	        touch "$${reqs}"
# Ensure frozen/pinned versions will subsequently be compiled
	        touch "./setup.cfg"
	    fi
	done
# Delegate parallel build all Python environments to tox.
	tox run-parallel --notest --pkg-only --parallel auto --parallel-live \
	    -e "build,$(TOX_ENV_LIST)"
	touch "$(@)"
# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`
./.tox/$(PYTHON_ENV)/log/editable.log: ./.tox/$(PYTHON_ENV)/bin/activate
	./.tox/$(PYTHON_ENV)/bin/pip install -e "./" | tee -a "$(@)"

# Perform any one-time local checkout set up
./var/log/host-install.log:
	mkdir -pv "$(dir $(@))"
	(
	    if ! which pip
	    then
	        if which apk
	        then
	            apk update
	            apk add "gettext" "py3-pip"
	        else
	            sudo apt-get update
	            sudo apt-get install -y "gettext-base" "python3-pip"
	        fi
	    fi
	    if [ -e ./requirements/$(PYTHON_ENV)/host.txt ]
	    then
	        pip install -r "./requirements/$(PYTHON_ENV)/host.txt"
	    else
	        pip install -r "./requirements/host.txt.in"
	    fi
	) | tee -a "$(@)"

./.git/hooks/pre-commit: ./.tox/$(PYTHON_ENV)/bin/activate
	./.tox/build/bin/pre-commit install \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push"

# Capture any project initialization tasks for reference.  Not actually usable.
./pyproject.toml:
	./.tox/build/bin/cz init

# Emacs editor settings
./.dir-locals.el: ./.dir-locals.el.in
	$(MAKE) -e "template=$(<)" "target=$(@)" expand-template

# User-created pre-requisites
~/.gitconfig:
	git config --global user.name "$(USER_FULL_NAME)"
	git config --global user.email "$(USER_EMAIL)"
~/.pypirc: ./home/.pypirc.in
	$(MAKE) -e "template=$(<)" "target=$(@)" expand-template
