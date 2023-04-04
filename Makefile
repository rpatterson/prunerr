## Development, build and maintenance tasks:
#
# To ease discovery for new contributors, variables that act as options affecting
# behavior are at the top.  Then skip to `## Top-level targets:` below to find targets
# intended for use by developers.  The real work, however, is in the recipes for real
# targets that follow.  If making changes here, please start by reading the philosophy
# commentary at the bottom of this file.

# Variables used as options to control behavior:
export TEMPLATE_IGNORE_EXISTING=false
# https://devguide.python.org/versions/#supported-versions
PYTHON_SUPPORTED_MINORS=3.11 3.10 3.9 3.8 3.7


## "Private" Variables:

# Variables that aren't likely to be of concern those just using and reading top-level
# targets.  Mostly variables whose values are derived from the environment or other
# values.  If adding a variable whose value isn't a literal constant or intended for use
# on the CLI as an option, add it to the appropriate grouping below.  Unfortunately,
# variables referenced in targets or prerequisites need to be defined above those
# references (as opposed to references in recipes), which means we can't move these
# further below for readability and discover.

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

# Values derived from the environment:
USER_NAME:=$(shell id -u -n)
USER_FULL_NAME:=$(shell \
    getent passwd "$(USER_NAME)" | cut -d ":" -f 5 | cut -d "," -f 1)
ifeq ($(USER_FULL_NAME),)
USER_FULL_NAME=$(USER_NAME)
endif
USER_EMAIL:=$(USER_NAME)@$(shell hostname --fqdn)

# Values concerning supported Python versions:
# Use the same Python version tox would as a default.
# https://tox.wiki/en/latest/config.html#base_python
PYTHON_HOST_MINOR:=$(shell \
    pip --version | sed -nE 's|.* \(python ([0-9]+.[0-9]+)\)$$|\1|p')
export PYTHON_HOST_ENV=py$(subst .,,$(PYTHON_HOST_MINOR))
# Determine the latest installed Python version of the supported versions
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

# Values derived from VCS/git:
VCS_BRANCH:=$(shell git branch --show-current)
# Make best guess at the right remote to use for comparison to determine release data:
VCS_REMOTE:=$(shell git-config "branch.$(VCS_BRANCH).remote")
ifeq ($(VCS_REMOTE),)
VCS_REMOTE:=$(shell git-config "branch.$(VCS_BRANCH).pushRemote")
endif
ifeq ($(VCS_REMOTE),)
VCS_REMOTE:=$(shell git config "remote.pushDefault")
endif
ifeq ($(VCS_REMOTE),)
VCS_REMOTE:=$(shell git config "checkout.defaultRemote")
endif
ifeq ($(VCS_REMOTE),)
VCS_REMOTE=origin
endif
# Support using a different remote and branch for comparison to determine release data:
VCS_COMPARE_BRANCH=$(VCS_BRANCH)
VCS_COMPARE_REMOTE=$(VCS_REMOTE)
# Assemble the targets used to avoid redundant fetches during release tasks:
VCS_FETCH_TARGETS=./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH)
ifneq ($(VCS_REMOTE)/$(VCS_BRANCH),$(VCS_COMPARE_REMOTE)/$(VCS_COMPARE_BRANCH))
VCS_FETCH_TARGETS+=./var/git/refs/remotes/$(VCS_COMPARE_REMOTE)/$(VCS_COMPARE_BRANCH)
endif

# Values used to run Tox:
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

# Values used for publishing releases:
# Safe defaults for testing the release process without publishing to the final/official
# hosts/indexes/registries:
RELEASE_PUBLISH=false
PYPI_REPO=testpypi
# Only publish releases from the `master` or `develop` branches:
ifeq ($(VCS_BRANCH),master)
RELEASE_PUBLISH=true
PYPI_REPO=pypi
else ifeq ($(VCS_BRANCH),develop)
# Publish pre-releases from the `develop` branch:
RELEASE_PUBLISH=true
PYPI_REPO=pypi
endif
# Address undefined variables warnings when running under local development
PYPI_PASSWORD=
export PYPI_PASSWORD
TEST_PYPI_PASSWORD=
export TEST_PYPI_PASSWORD

# Done with `$(shell ...)`, echo recipe commands going forward
.SHELLFLAGS+= -x


## Makefile "functions":
#
# Snippets whose output is frequently used including across recipes.  Used for output
# only, not actually making any changes.
# https://www.gnu.org/software/make/manual/html_node/Call-Function.html

# Return the most recently built package:
current_pkg = $(shell ls -t ./.tox/.pkg/dist/*$(1) | head -n 1)


## Top-level targets:

.PHONY: all
### The default target.
all: build


## Build Targets:
#
# Recipes that make artifacts needed for by end-users, development tasks, other recipes.

.PHONY: build
### Perform any currently necessary local set-up common to most operations.
build: \
	./.git/hooks/pre-commit \
	$(HOME)/.local/var/log/python-project-structure-host-install.log
	$(MAKE) -e -j $(PYTHON_ENVS:%=build-requirements-%)
.PHONY: $(PYTHON_ENVS:%=build-requirements-%)
### Compile fixed/pinned dependency versions if necessary.
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

.PHONY: build-pkgs
### Ensure the built package is current when used outside of tox.
build-pkgs: ./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH)
# Defined as a .PHONY recipe so that multiple targets can depend on this as a
# pre-requisite and it will only be run once per invocation.
	tox run -e "$(PYTHON_ENV)" --pkg-only
# Also build the source distribution:
	tox run -e "$(PYTHON_ENV)" --override "testenv.package=sdist" --pkg-only


## Test Targets:
#
# Recipes that run the test suite.

.PHONY: test
### Run the full suite of tests, coverage checks, and linters.
test: build
	tox $(TOX_RUN_ARGS) -e "$(TOX_ENV_LIST)"

.PHONY: test-debug
### Run tests directly on the host and invoke the debugger on errors/failures.
test-debug: ./var/log/tox/$(PYTHON_ENV)/editable.log
	$(TOX_EXEC_ARGS) pytest --pdb


## Release Targets:
#
# Recipes that make an changes needed for releases and publish built artifacts to
# end-users.

.PHONY: release
### Publish installable Python packages to PyPI.
release: $(HOME)/.local/var/log/python-project-structure-host-install.log build-pkgs \
		~/.pypirc
# https://twine.readthedocs.io/en/latest/#using-twine
	$(TOX_EXEC_BUILD_ARGS) twine check \
	    "$(call current_pkg,.whl)" "$(call current_pkg,.tar.gz)"
	$(MAKE) "check-clean"
# Only release from the `master` or `develop` branches:
ifeq ($(RELEASE_PUBLISH),true)
# https://twine.readthedocs.io/en/latest/#using-twine
	$(TOX_EXEC_BUILD_ARGS) twine upload -s -r "$(PYPI_REPO)" \
	    "$(call current_pkg,.whl)" "$(call current_pkg,.tar.gz)"
endif

.PHONY: release-bump
### Bump the package version if on a branch that should trigger a release.
release-bump: ~/.gitconfig ./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH) \
		$(HOME)/.local/var/log/python-project-structure-host-install.log
	if ! git diff --cached --exit-code
	then
	    set +x
	    echo "CRITICAL: Cannot bump version with staged changes"
	    false
	fi
# Check if the conventional commits since the last release require new release and thus
# a version bump:
	exit_code=0
	$(TOX_EXEC_BUILD_ARGS) python ./bin/cz-check-bump || exit_code=$$?
	if (( $$exit_code == 3 || $$exit_code == 21 ))
	then
# No release necessary for the commits since the last release, don't publish a release
	    exit
	elif (( $$exit_code != 0 ))
	then
# Commitizen returned an unexpected exit status code, fail
	    exit $$exit_code
	fi
# Collect the versions involved in this release according to conventional commits:
	cz_bump_args="--check-consistency --no-verify"
ifneq ($(VCS_BRANCH),master)
	cz_bump_args+=" --prerelease beta"
endif
ifeq ($(RELEASE_PUBLISH),true)
# Build and stage the release notes to be commited by `$ cz bump`
	next_version=$$(
	    $(TOX_EXEC_BUILD_ARGS) cz bump $${cz_bump_args} --yes --dry-run |
	    sed -nE 's|.* ([^ ]+) *→ *([^ ]+).*|\2|p'
	) || true
	$(TOX_EXEC_ARGS) towncrier build --version "$${next_version}" --yes
# Increment the version in VCS
	$(TOX_EXEC_BUILD_ARGS) cz bump $${cz_bump_args}
# The VCS remote should reflect the release before the release is published to ensure
# that a published release is never *not* reflected in VCS.
	git push --no-verify --tags "$(VCS_REMOTE)" "HEAD:$(VCS_BRANCH)"
endif


## Check Targets:
#
# Recipes that confirm development conditions.

.PHONY: check-push
### Perform any checks that should only be run before pushing.
check-push: $(VCS_FETCH_TARGETS) \
		$(HOME)/.local/var/log/python-project-structure-host-install.log
	exit_code=0
	$(TOX_EXEC_BUILD_ARGS) cz check --rev-range \
	    "$(VCS_COMPARE_REMOTE)/$(VCS_COMPARE_BRANCH)..HEAD" || exit_code=$$?
	if ! (( $$exit_code == 3 || $$exit_code == 21 ))
	then
	    exit $$exit_code
	fi
	if $(TOX_EXEC_BUILD_ARGS) python ./bin/cz-check-bump \
	    "$(VCS_COMPARE_REMOTE)/$(VCS_COMPARE_BRANCH)"
	then
	    $(TOX_EXEC_ARGS) towncrier check --compare-with \
		"$(VCS_COMPARE_REMOTE)/$(VCS_COMPARE_BRANCH)"
	fi

.PHONY: check-clean
### Confirm that the checkout is free of uncommitted VCS changes.
check-clean: $(HOME)/.local/var/log/python-project-structure-host-install.log
	if [ -n "$$(git status --porcelain)" ]
	then
	    set +x
	    echo "Checkout is not clean"
	    false
	fi


## Development Targets:
#
# Recipes used by developers to make changes to the code.

.PHONY: devel-format
### Automatically correct code in this checkout according to linters and style checkers.
devel-format: $(HOME)/.local/var/log/python-project-structure-host-install.log
	$(TOX_EXEC_ARGS) autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables "./src/pythonprojectstructure/"
	$(TOX_EXEC_ARGS) autopep8 -v -i -r "./src/pythonprojectstructure/"
	$(TOX_EXEC_ARGS) black "./src/pythonprojectstructure/"

.PHONY: devel-upgrade
### Update all fixed/pinned dependencies to their latest available versions.
devel-upgrade:
	touch "./setup.cfg" "./requirements/build.txt.in" "./build-host/requirements.txt.in"
	$(MAKE) -e -j $(PYTHON_ENVS:%=build-requirements-%)
# Update VCS hooks from remotes to the latest tag.
	$(TOX_EXEC_BUILD_ARGS) pre-commit autoupdate

.PHONY: devel-upgrade-branch
### Reset an upgrade branch, commit upgraded dependencies on it, and push for review.
devel-upgrade-branch: ~/.gitconfig ./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH)
	remote_branch_exists=false
	if git fetch "$(VCS_REMOTE)" "$(VCS_BRANCH)-upgrade"
	then
	    remote_branch_exists=true
	fi
	if git show-ref -q --heads "$(VCS_BRANCH)-upgrade"
	then
# Reset an existing local branch to the latest upstream before upgrading
	    git checkout "$(VCS_BRANCH)-upgrade"
	    git reset --hard "$(VCS_BRANCH)"
	else
# Create a new local branch from the latest upstream before upgrading
	    git checkout -b "$(VCS_BRANCH)-upgrade" "$(VCS_BRANCH)"
	fi
	now=$$(date -u)
	$(MAKE) TEMPLATE_IGNORE_EXISTING="true" devel-upgrade
	if $(MAKE) "check-clean"
	then
# No changes from upgrade, exit successfully but push nothing
	    exit
	fi
# Commit the upgrade changes
	echo "Upgrade all requirements to the latest versions as of $${now}." \
	    >"./src/pythonprojectstructure/newsfragments/upgrade-requirements.bugfix.rst"
	git add --update './build-host/requirements-*.txt' './requirements/*/*.txt' \
	    "./.pre-commit-config.yaml"
	git add \
	    "./src/pythonprojectstructure/newsfragments/upgrade-requirements.bugfix.rst"
	git commit --all --signoff -m \
	    "fix(deps): Upgrade requirements latest versions"
# Fail if upgrading left untracked files in VCS
	$(MAKE) "check-clean"
# Push any upgrades to the remote for review.  Specify both the ref and the expected ref
# for `--force-with-lease=...` to support pushing to multiple mirrors/remotes via
# multiple `pushUrl`:
	git_push_args="--no-verify"
	if [ "$${remote_branch_exists=true}" == "true" ]
	then
	    git_push_args+=" --force-with-lease=\
	$(VCS_BRANCH)-upgrade:$(VCS_REMOTE)/$(VCS_BRANCH)-upgrade"
	fi
	git push $${git_push_args} "$(VCS_REMOTE)" "HEAD:$(VCS_BRANCH)-upgrade"


## Clean Targets:
#
# Recipes used to restore the checkout to initial conditions.

.PHONY: clean
### Restore the checkout to a state as close to an initial clone as possible.
clean:
	$(TOX_EXEC_BUILD_ARGS) pre-commit uninstall \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push" \
	    || true
	$(TOX_EXEC_BUILD_ARGS) pre-commit clean || true
	git clean -dfx -e "var/"
	rm -rfv "./var/log/"


## Real Targets:
#
# Recipes that make actual changes and create and update files for the target.

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

# Targets used as pre-requisites to ensure virtual environments managed by tox have been
# created and can be used directly to save time on Tox's overhead when we don't need
# Tox's logic about when to update/recreate them, e.g.:
#     $ ./.tox/build/bin/cz --help
# Mostly useful for build/release tools.
$(PYTHON_ALL_ENVS:%=./var/log/tox/%/build.log): \
		$(HOME)/.local/var/log/python-project-structure-host-install.log
	mkdir -pv "$(dir $(@))"
	tox run $(TOX_EXEC_OPTS) -e "$(@:var/log/tox/%/build.log=%)" --notest |
	    tee -a "$(@)"
# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`.  Use as a
# prerequisite when using Tox-managed virtual environments directly and changes to code
# need to take effect immediately.
$(PYTHON_ENVS:%=./var/log/tox/%/editable.log):
	$(MAKE) "$(HOME)/.local/var/log/python-project-structure-host-install.log"
	mkdir -pv "$(dir $(@))"
	tox exec $(TOX_EXEC_OPTS) -e "$(@:var/log/tox/%/editable.log=%)" -- \
	    pip install -e "./" | tee -a "$(@)"

# Install all tools required by recipes that have to be installed externally on the
# host.  Use a target file outside this checkout to support multiple checkouts.  Use a
# target specific to this project so that other projects can use the same approach but
# with different requirements.
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

# Retrieve VCS data needed for versioning (tags) and release (release notes).
$(VCS_FETCH_TARGETS):
	git_fetch_args=--tags
	if [ "$$(git rev-parse --is-shallow-repository)" == "true" ]
	then
	    git_fetch_args+=" --unshallow"
	fi
	mkdir -pv "$(dir $(@))"
	(git fetch $${git_fetch_args} \
	    "$(notdir $(patsubst %/,%,$(dir $(@))))" "$(notdir $(@))" || true) |&
	    tee -a "$(@)"
./.git/hooks/pre-commit:
	$(MAKE) "$(HOME)/.local/var/log/python-project-structure-host-install.log"
	$(TOX_EXEC_BUILD_ARGS) pre-commit install \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push"

# Capture any project initialization tasks for reference.  Not actually usable.
./pyproject.toml:
	$(MAKE) "$(HOME)/.local/var/log/python-project-structure-host-install.log"
	$(TOX_EXEC_BUILD_ARGS) cz init

# Tell Emacs where to find checkout-local tools needed to check the code.
./.dir-locals.el: ./.dir-locals.el.in
	$(MAKE) -e "template=$(<)" "target=$(@)" expand-template

# Ensure minimal VCS configuration, mostly useful in automation such as CI.
~/.gitconfig:
	git config --global user.name "$(USER_FULL_NAME)"
	git config --global user.email "$(USER_EMAIL)"

# Ensure release publishing authentication, mostly useful in automation such as CI.
~/.pypirc: ./home/.pypirc.in
	$(MAKE) -e "template=$(<)" "target=$(@)" expand-template


## Utility Targets:
#
# Recipes used to make similar changes across targets where using Make's basic syntax
# can't be used.

.PHONY: expand-template
## Create a file from a template replacing environment variables
expand-template:
	$(MAKE) "$(HOME)/.local/var/log/python-project-structure-host-install.log"
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


## Makefile Development:
#
# Development primarily requires a balance of 2 priorities:
#
# - Ensure the correctness of the code and build artifacts
# - Minimize iteration time overhead in the inner loop of development
#
# This project uses Make to balance those priorities.  Target recipes capture the
# commands necessary to build artifacts, run tests, and check the code.  Top-level
# targets assemble those recipes to put it all together and ensure correctness.  Target
# prerequisites are used to define when build artifacts need to be updated so that
# time isn't wasted on unnecessary updates in the inner loop of development.
#
# The most important Make concept to understand if making changes here is that of real
# targets and prerequisites, as opposed to "phony" targets.  The target is only updated
# if any of its prerequisites are newer, IOW have a more recent modification time, than
# the target.  For example, if a new feature adds library as a new project dependency
# then correctness requires that the fixed/pinned versions be updated to include the new
# library.  Most of the time, however, the fixed/pinned versions don't need to be
# updated and it would waste significant time to always update them in the inner loop of
# development.  We express this relationship in Make by defining the files containing
# the fixed/pinned versions as targets and the `./setup.cfg` file where dependencies are
# defined as a prerequisite:
#
#    ./requirements.txt: setup.cfg
#        ./.tox/py310/bin/pip-compile --output-file "$(@)" "$(<)"
#
# To that end, developers should use real target files whenever possible when adding
# recipes to this file.
#
# Sometimes the task we need a recipe to accomplish should only be run when certain
# changes have been made and as such we can use those changed files as prerequisites but
# the task doesn't produce an artifact appropriate for use as the target for the recipe.
# In that case, the recipe can write "simulated" artifact such as by piping output to a
# log file:
#
#     ./var/log/foo.log:
#         mkdir -pv "$(dir $(@))"
#         ./.tox/build/bin/python "./bin/foo.py" | tee -a "$(@)"
#
# This is also useful when none of the modification times of produced artifacts can be
# counted on to correctly reflect when any subsequent targets need to be updated when
# using this target as a pre-requisite in turn.  If no output can be captured, then the
# recipe can create arbitrary output:
#
#     ./var/log/foo.log:
#         ./.tox/build/bin/python "./bin/foo.py"
#         mkdir -pv "$(dir $(@))"
#         date | tee -a "$(@)"
#
# We use a few more Make features than this core feature and welcome further use of such
# features:
#
# - `$(@)`:
#   The automatic variable containing the file path for the target
#
# - `$(<)`:
#   The automatic variable containing the file path for the first prerequisite
#
# - `$(FOO:%=foo-%)`:
#   Substitution references to generate transformations of space-separated values
#
# - `$ make FOO=bar ...`:
#   Overriding variables on the command-line when invoking make as "options"
#
# We want to avoid, however, using many more features of Make, particularly the more
# "magical" features, to keep it readable, discover-able, and otherwise accessible to
# developers who may not have significant familiarity with Make.  If there's a good,
# pragmatic reason to add use of further features feel free to make the case but avoid
# them if possible.
