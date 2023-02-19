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
export TEMPLATE_IGNORE_EXISTING=false
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
PYTHON_HOST_MINOR:=$(shell pip --version | sed -nE 's|.* \(python ([0-9]+.[0-9]+)\)$$|\1|p')
export PYTHON_HOST_ENV=py$(subst .,,$(PYTHON_HOST_MINOR))
# Determine the latest installed Python version of the supported versions
PYTHON_BASENAMES=$(PYTHON_SUPPORTED_MINORS:%=python%)
define PYTHON_AVAIL_EXECS :=
    $(foreach PYTHON_BASENAME,$(PYTHON_BASENAMES),$(shell which $(PYTHON_BASENAME)))
endef
PYTHON_LATEST_EXEC=$(firstword $(PYTHON_AVAIL_EXECS))
PYTHON_LATEST_BASENAME=$(notdir $(PYTHON_LATEST_EXEC))
PYTHON_MINOR=$(PYTHON_HOST_MINOR)
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
PYTHON_ALL_ENVS=$(PYTHON_ENVS) build
TOX_ENV_LIST=$(subst $(EMPTY) ,$(COMMA),$(PYTHON_ENVS))
TOX_RUN_ARGS=run-parallel --parallel auto --parallel-live
ifeq ($(words $(PYTHON_MINORS)),1)
TOX_RUN_ARGS=run
endif
# The options that allow for rapid execution of arbitrary commands in the venvs managed
# by tox
TOX_EXEC_OPTS=--no-recreate-pkg --skip-pkg-install
TOX_EXEC_ARGS=tox exec $(TOX_EXEC_OPTS) -e "$(PYTHON_ENV)" --
TOX_EXEC_BUILD_ARGS=tox exec $(TOX_EXEC_OPTS) -e "build" --

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
	./.git/hooks/pre-commit \
	$(HOME)/.local/var/log/python-project-structure-host-install.log
ifeq ($(RELEASE_PUBLISH),true)
	if [ -e "./build/next-version.txt" ]
	then
# Ensure the build is made from the version bump commit if it was done elsewhere:
	    git pull --ff-only "origin" "v$$(cat "./build/next-version.txt")"
	fi
endif
	$(MAKE) -e -j $(PYTHON_ENVS:%=build-requirements-%)
.PHONY: $(PYTHON_ENVS:%=build-requirements-%)
### Compile fixed/pinned dependency versions if necessary
$(PYTHON_ENVS:%=build-requirements-%):
# Avoid parallel tox recreations stomping on each other
	$(MAKE) "$(@:build-requirements-%=./var/log/tox/%/build.log)"
	targets="./requirements/$(@:build-requirements-%=%)/user.txt \
	    ./requirements/$(@:build-requirements-%=%)/devel.txt \
	    ./requirements/$(@:build-requirements-%=%)/build.txt \
	    ./build-host/requirements-$(@:build-requirements-%=%).txt"
# Workaround race conditions in pip's HTTP file cache:
# https://github.com/pypa/pip/issues/6970#issuecomment-527678672
	$(MAKE) -e -j $${targets} ||
	    $(MAKE) -e -j $${targets} ||
	    $(MAKE) -e -j $${targets}
.PHONY: build-bump
### Bump the package version if on a branch that should trigger a release
build-bump: \
	~/.gitconfig $(HOME)/.local/var/log/python-project-structure-host-install.log
# Retrieve VCS data needed for versioning (tags) and release (release notes)
	git fetch --tags --unshallow origin "$(TOWNCRIER_COMPARE_BRANCH)"
# Collect the versions involved in this release according to conventional commits
	cz_bump_args="--check-consistency --no-verify"
ifneq ($(VCS_BRANCH),master)
	cz_bump_args+=" --prerelease beta"
endif
# Run first in case any input is needed from the developer
	exit_code=0
	$(TOX_EXEC_BUILD_ARGS) cz bump $${cz_bump_args} --dry-run || exit_code=$$?
# Check if a release and thus a version bump is needed for the commits since the last
# release:
	next_version=$$(
	    $(TOX_EXEC_BUILD_ARGS) cz bump $${cz_bump_args} --yes --dry-run |
	    sed -nE 's|.* ([^ ]+) *→ *([^ ]+).*|\2|p'
	) || true
	rm -fv "./build/next-version.txt"
	if (( $$exit_code == 3 || $$exit_code == 21 ))
	then
# No release necessary for the commits since the last release, don't publish a release
	    exit
	elif (( $$exit_code == 0 ))
	then
	    mkdir -pv "./build/"
	    echo "$${next_version}" >"./build/next-version.txt"
	else
# Commitizen returned an unexpected exit status code, fail
	    exit $$exit_code
	fi
# Update the release notes/changelog
	$(TOX_EXEC_ARGS) towncrier check \
	    --compare-with "origin/$(TOWNCRIER_COMPARE_BRANCH)"
	if ! git diff --cached --exit-code
	then
	    set +x
	    echo "CRITICAL: Cannot bump version with staged changes"
	    false
	fi
# Build and stage the release notes to be commited by `$ cz bump`
	$(TOX_EXEC_ARGS) towncrier build --version "$${next_version}" --yes
# Increment the version in VCS
	$(TOX_EXEC_BUILD_ARGS) cz bump $${cz_bump_args}
# Prevent uploading unintended distributions
	rm -vf ./.tox/.pkg/dist/*
ifeq ($(RELEASE_PUBLISH),true)
# The VCS remote should reflect the release before the release is published to ensure
# that a published release is never *not* reflected in VCS.
	git push --no-verify -o "ci.skip" --tags "origin" "HEAD:$(VCS_BRANCH)"
endif

.PHONY: check-push
### Perform any checks that should only be run before pushing
check-push: $(HOME)/.local/var/log/python-project-structure-host-install.log
	$(TOX_EXEC_ARGS) towncrier check --compare-with "origin/$(TOWNCRIER_COMPARE_BRANCH)"
.PHONY: check-clean
### Confirm that the checkout is free of uncommitted VCS changes
check-clean: $(HOME)/.local/var/log/python-project-structure-host-install.log
	if [ -n "$$(git status --porcelain)" ]
	then
	    set +x
	    echo "CRITICAL: Checkout is not clean, not publishing release"
	    false
	fi

.PHONY: release
### Publish installable Python packages to PyPI
release: $(HOME)/.local/var/log/python-project-structure-host-install.log ~/.pypirc
ifeq ($(RELEASE_PUBLISH),true)
# Ensure the release is made from the version bump commit if it was done elsewhere:
	git pull --ff-only "origin" "v$$(cat "./build/next-version.txt")"
endif
# Build the actual release artifacts, tox builds the `sdist` so here we build the wheel
	$(TOX_EXEC_ARGS) pyproject-build --outdir "./.tox/.pkg/dist/" -w
# https://twine.readthedocs.io/en/latest/#using-twine
	$(TOX_EXEC_BUILD_ARGS) twine check ./.tox/.pkg/dist/python?project?structure-*
	$(MAKE) "check-clean"
	if [ ! -e "./build/next-version.txt" ]
	then
	    exit
	fi
# Only release from the `master` or `develop` branches:
ifeq ($(RELEASE_PUBLISH),true)
# https://twine.readthedocs.io/en/latest/#using-twine
	$(TOX_EXEC_BUILD_ARGS) twine upload -s -r "$(PYPI_REPO)" \
	    ./.tox/.pkg/dist/python?project?structure-*
endif

.PHONY: format
### Automatically correct code in this checkout according to linters and style checkers
format: $(HOME)/.local/var/log/python-project-structure-host-install.log
	$(TOX_EXEC_ARGS) autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables "./src/pythonprojectstructure/"
	$(TOX_EXEC_ARGS) autopep8 -v -i -r "./src/pythonprojectstructure/"
	$(TOX_EXEC_ARGS) black "./src/pythonprojectstructure/"

.PHONY: test
### Run the full suite of tests, coverage checks, and linters
test: build
	tox $(TOX_RUN_ARGS) -e "$(TOX_ENV_LIST)"

.PHONY: test-debug
### Run tests in the main/default environment and invoke the debugger on errors/failures
test-debug: ./var/log/tox/$(PYTHON_ENV)/editable.log
	$(TOX_EXEC_ARGS) pytest --pdb

.PHONY: upgrade
### Update all fixed/pinned dependencies to their latest available versions
upgrade:
	touch "./setup.cfg" "./requirements/build.txt.in" "./build-host/requirements.txt.in"
	$(MAKE) -e -j $(PYTHON_ENVS:%=build-requirements-%)
# Update VCS hooks from remotes to the latest tag.
	$(TOX_EXEC_BUILD_ARGS) pre-commit autoupdate
.PHONY: upgrade-branch
### Reset an upgrade branch, commit upgraded dependencies on it, and push for review
upgrade-branch: ~/.gitconfig
	git fetch "origin" "$(VCS_BRANCH)"
	git fetch "origin" "$(VCS_BRANCH)-upgrade"
	if git show-ref -q --heads "$(VCS_BRANCH)-upgrade"
	then
# Reset an existing local branch to the latest upstream before upgrading
	    git checkout "$(VCS_BRANCH)-upgrade"
	    git reset --hard "origin/$(VCS_BRANCH)"
	else
# Create a new local branch from the latest upstream before upgrading
	    git checkout -b "$(VCS_BRANCH)-upgrade" "origin/$(VCS_BRANCH)"
	fi
	$(MAKE) TEMPLATE_IGNORE_EXISTING="true" upgrade
	if $(MAKE) "check-clean"
	then
# No changes from upgrade, exit successfully but push nothing
	    exit
	fi
# Commit the upgrade changes
	echo "Upgrade all requirements and dependencies to the latest versions." \
	    >"./src/pythonprojectstructure/newsfragments/upgrade-requirements.misc.rst"
	git add --update \
	    './build-host/requirements-*.txt' './requirements/*/build.txt' \
	    "./.pre-commit-config.yaml"
	git add \
	    "./src/pythonprojectstructure/newsfragments/upgrade-requirements.misc.rst"
	git commit --all --signoff -m \
	    "build(deps): Upgrade requirements latest versions"
# Fail if upgrading left untracked files in VCS
	$(MAKE) "check-clean"
# Push any upgrades to the remote for review.  Specify both the ref and the expected ref
# for `--force-with-lease=...` to support pushing to multiple mirrors/remotes via
# multiple `pushUrl`:
	git push \
	    --force-with-lease="$(VCS_BRANCH)-upgrade:origin/$(VCS_BRANCH)-upgrade" \
	    --no-verify "origin" "HEAD:$(VCS_BRANCH)-upgrade"

.PHONY: clean
### Restore the checkout to a state as close to an initial clone as possible
clean:
	$(TOX_EXEC_BUILD_ARGS) pre-commit uninstall \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push" \
	    || true
	$(TOX_EXEC_BUILD_ARGS) pre-commit clean || true
	git clean -dfx -e "var/"
	rm -rfv "./var/log/"


## Utility targets

.PHONY: expand-template
## Create a file from a template replacing environment variables
expand-template: $(HOME)/.local/var/log/python-project-structure-host-install.log
	set +x
	if [ -e "$(target)" ]
	then
ifeq ($(TEMPLATE_IGNORE_EXISTING),true)
	    exit
else
	    envsubst <"$(template)" | diff -u "$(target)" "-" || true
	    echo "ERROR: Template $(template) has been updated:"
	    echo "       Reconcile changes and \`$$ touch $(target)\`:"
	    false
endif
	fi
	envsubst <"$(template)" >"$(target)"


## Real targets

# Manage fixed/pinned versions in `./requirements/**.txt` files.  Has to be run for each
# python version in the virtual environment for that Python version:
# https://github.com/jazzband/pip-tools#cross-environment-usage-of-requirementsinrequirementstxt-and-pip-compile
$(PYTHON_ENVS:%=./requirements/%/devel.txt): ./pyproject.toml ./setup.cfg ./tox.ini
	true DEBUG Updated prereqs: $(?)
	$(MAKE) "$(@:requirements/%/devel.txt=./var/log/tox/%/build.log)"
	./.tox/$(@:requirements/%/devel.txt=%)/bin/pip-compile \
	    --resolver "backtracking" --upgrade --extra "devel" \
	    --output-file "$(@)" "$(<)"
$(PYTHON_ENVS:%=./requirements/%/user.txt): ./pyproject.toml ./setup.cfg ./tox.ini
	true DEBUG Updated prereqs: $(?)
	$(MAKE) "$(@:requirements/%/user.txt=./var/log/tox/%/build.log)"
	./.tox/$(@:requirements/%/user.txt=%)/bin/pip-compile \
	    --resolver "backtracking" --upgrade --output-file "$(@)" "$(<)"
$(PYTHON_ENVS:%=./build-host/requirements-%.txt): ./build-host/requirements.txt.in
	true DEBUG Updated prereqs: $(?)
	$(MAKE) "$(@:build-host/requirements-%.txt=./var/log/tox/%/build.log)"
	./.tox/$(@:build-host/requirements-%.txt=%)/bin/pip-compile \
	    --resolver "backtracking" --upgrade --output-file "$(@)" "$(<)"
# Only update the installed tox version for the latest/host/main/default Python version
	if [ "$(@:build-host/requirements-%.txt=%)" = "$(PYTHON_ENV)" ]
	then
# Don't install tox into one of it's own virtual environments
	    if [ -n "$${VIRTUAL_ENV:-}" ]
	    then
	        pip_bin="$$(which -a pip | grep -v "^$${VIRTUAL_ENV}/bin/" | head -n 1)"
	    else
	        pip_bin="pip"
	    fi
	    "$${pip_bin}" install -r "$(@)"
	fi
$(PYTHON_ENVS:%=./requirements/%/build.txt): ./requirements/build.txt.in
	true DEBUG Updated prereqs: $(?)
	$(MAKE) "$(@:requirements/%/build.txt=./var/log/tox/%/build.log)"
	./.tox/$(@:requirements/%/build.txt=%)/bin/pip-compile \
	    --resolver "backtracking" --upgrade --output-file "$(@)" "$(<)"

# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`
$(PYTHON_ALL_ENVS:%=./var/log/tox/%/build.log): \
		$(HOME)/.local/var/log/python-project-structure-host-install.log
	mkdir -pv "$(dir $(@))"
	tox exec $(TOX_EXEC_OPTS) -e "$(@:var/log/tox/%/build.log=%)" -- python -c "" |
	    tee -a "$(@)"
$(PYTHON_ENVS:%=./var/log/tox/%/editable.log):
	$(MAKE) "$(HOME)/.local/var/log/python-project-structure-host-install.log"
	mkdir -pv "$(dir $(@))"
	tox exec $(TOX_EXEC_OPTS) -e "$(@:var/log/tox/%/editable.log=%)" -- \
	    pip install -e "./" | tee -a "$(@)"

# Perform any one-time local checkout set up
$(HOME)/.local/var/log/python-project-structure-host-install.log:
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
	    if [ -e ./build-host/requirements-$(PYTHON_HOST_ENV).txt ]
	    then
	        pip install -r "./build-host/requirements-$(PYTHON_HOST_ENV).txt"
	    else
	        pip install -r "./build-host/requirements.txt.in"
	    fi
	) | tee -a "$(@)"

./.git/hooks/pre-commit:
	$(MAKE) "$(HOME)/.local/var/log/python-project-structure-host-install.log"
	$(TOX_EXEC_BUILD_ARGS) pre-commit install \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push"

# Capture any project initialization tasks for reference.  Not actually usable.
./pyproject.toml:
	$(MAKE) "$(HOME)/.local/var/log/python-project-structure-host-install.log"
	$(TOX_EXEC_BUILD_ARGS) cz init

# Emacs editor settings
./.dir-locals.el: ./.dir-locals.el.in
	$(MAKE) -e "template=$(<)" "target=$(@)" expand-template

# User-created pre-requisites
~/.gitconfig:
	git config --global user.name "$(USER_FULL_NAME)"
	git config --global user.email "$(USER_EMAIL)"
~/.pypirc: ./home/.pypirc.in
	$(MAKE) -e "template=$(<)" "target=$(@)" expand-template
