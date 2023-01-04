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
export DOCKER_USER=merpatterson
# Project-specific variables
GPG_SIGNING_KEYID=2EFF7CCE6828E359
GITHUB_REPOSITORY_OWNER=rpatterson
CI_REGISTRY_IMAGE=registry.gitlab.com/$(GITHUB_REPOSITORY_OWNER)/python-project-structure

# Values derived from the environment
USER_NAME:=$(shell id -u -n)
USER_FULL_NAME:=$(shell getent passwd "$(USER_NAME)" | cut -d ":" -f 5 | cut -d "," -f 1)
ifeq ($(USER_FULL_NAME),)
USER_FULL_NAME=$(USER_NAME)
endif
USER_EMAIL:=$(USER_NAME)@$(shell hostname -f)
export PUID:=$(shell id -u)
export PGID:=$(shell id -g)
export CHECKOUT_DIR=$(PWD)
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
TOX_ENV_LIST=$(subst $(EMPTY) ,$(COMMA),$(PYTHON_ENVS))
export TOX_RUN_ARGS=run-parallel --parallel auto --parallel-live
ifeq ($(words $(PYTHON_MINORS)),1)
export TOX_RUN_ARGS=run
endif
# The options that allow for rapid execution of arbitrary commands in the venvs managed
# by tox
TOX_EXEC_OPTS=--no-recreate-pkg --skip-pkg-install
TOX_EXEC_ARGS=tox exec $(TOX_EXEC_OPTS) -e "$(PYTHON_ENV)" --
TOX_EXEC_BUILD_ARGS=tox exec $(TOX_EXEC_OPTS) -e "build" --
DOCKER_BUILD_ARGS=

# Safe defaults for testing the release process without publishing to the final/official
# hosts/indexes/registries:
PIP_COMPILE_ARGS=--upgrade
RELEASE_PUBLISH=false
TOWNCRIER_COMPARE_BRANCH=develop
PYPI_REPO=testpypi
PYPI_HOSTNAME=test.pypi.org
# Determine which branch is checked out depending on the environment
GITLAB_CI=false
GITHUB_ACTIONS=false
ifeq ($(GITLAB_CI),true)
USER_EMAIL=$(USER_NAME)@runners-manager.gitlab.com
VCS_BRANCH=$(CI_COMMIT_REF_NAME)
else ifeq ($(GITHUB_ACTIONS),true)
USER_EMAIL=$(USER_NAME)@actions.github.com
VCS_BRANCH=$(GITHUB_REF_NAME)
else
VCS_BRANCH:=$(shell git branch --show-current)
endif
# Only publish releases from the `master` or `develop` branches:
DOCKER_PUSH=false
CI=false
GITHUB_RELEASE_ARGS=--prerelease
ifeq ($(CI),true)
# Compile requirements on CI/CD as a check to make sure all changes to dependencies have
# been reflected in the frozen/pinned versions, but don't upgrade packages so that
# external changes, such as new PyPI releases, don't turn CI/CD red spuriously and
# unrelated to the contributor's actual changes.
PIP_COMPILE_ARGS=
endif
ifeq ($(GITLAB_CI),true)
ifeq ($(VCS_BRANCH),master)
RELEASE_PUBLISH=true
TOWNCRIER_COMPARE_BRANCH=master
PYPI_REPO=pypi
PYPI_HOSTNAME=pypi.org
DOCKER_PUSH=true
GITHUB_RELEASE_ARGS=
else ifeq ($(VCS_BRANCH),develop)
# Publish pre-releases from the `develop` branch:
RELEASE_PUBLISH=true
endif
endif
# Address undefined variables warnings when running under local development
VCS_REMOTE_PUSH_URL=
CODECOV_TOKEN=
PROJECT_GITHUB_PAT=

# Done with `$(shell ...)`, echo recipe commands going forward
.SHELLFLAGS+= -x


## Top-level targets

.PHONY: all
### Default target
all: build

# Strive for as much consistency as possible in development tasks between the local host
# and inside containers.  To that end, most of the `*-docker` container target recipes
# should run the corresponding `*-local` local host target recipes inside the
# development container.  Top level targets, like `test`, should run as much as possible
# inside the development container.

.PHONY: build
### Set up everything for development from a checkout, local and in containers
build: ./.git/hooks/pre-commit build-docker
.PHONY: build-docker
### Set up for development in Docker containers
build-docker: ./.env
	$(MAKE) ./var/log/host-install.log
	$(MAKE) -e -j DOCKER_BUILD_ARGS="--progress plain" \
	    $(PYTHON_MINORS:%=build-docker-%)
.PHONY: $(PYTHON_MINORS:%=build-docker-%)
### Set up for development in a Docker container for one Python version
$(PYTHON_MINORS:%=build-docker-%):
	$(MAKE) -e PYTHON_MINORS="$(@:build-docker-%=%)" \
	    PYTHON_ENV="py$(subst .,,$(@:build-docker-%=%))" \
	    "./var/docker/py$(subst .,,$(@:build-docker-%=%))/log/build.log"
.PHONY: $(PYTHON_ENVS:%=build-requirements-%)
### Compile fixed/pinned dependency versions if necessary
$(PYTHON_ENVS:%=build-requirements-%):
# Avoid parallel tox recreations stomping on each other
	tox exec $(TOX_EXEC_OPTS) -e "$(@:build-requirements-%=%)" -- python -c ""
# Parallelizing all `$ pip-compile` runs seems to fail intermittently with:
#     WARNING: Skipping page https://pypi.org/simple/wheel/ because the GET request got
#     Content-Type: .  The only supported Content-Type is text/html
# I assume it's some sort of PyPI rate limiting.  Remove the next `$ make -j` option if
# you don't find the trade off worth it.
	$(MAKE) -e -j \
	    "./requirements/$(@:build-requirements-%=%)/user.txt" \
	    "./requirements/$(@:build-requirements-%=%)/devel.txt" \
	    "./requirements/$(@:build-requirements-%=%)/build.txt" \
	    "./requirements/$(@:build-requirements-%=%)/host.txt"
.PHONY: build-wheel
### Build the package/distribution format that is fastest to install
build-wheel: ./var/docker/$(PYTHON_ENV)/log/build.log
	ln -sfv "$$(
	    docker compose run --rm python-project-structure-devel pyproject-build -w |
	    sed -nE 's|^Successfully built (.+\.whl)$$|\1|p'
	)" "./dist/.current.whl"
.PHONY: build-bump
### Bump the package version if on a branch that should trigger a release
build-bump: \
		~/.gitconfig ./var/log/host-install.log \
		./var/docker/$(PYTHON_ENV)/log/build.log
ifeq ($(RELEASE_PUBLISH),true)
	set +x
ifneq ($(VCS_REMOTE_PUSH_URL),)
# Requires a Personal or Project Access Token in the GitLab CI/CD Variables.  That
# variable value should be prefixed with the token name as a HTTP `user:password`
# authentication string:
# https://stackoverflow.com/a/73426417/624787
	git remote set-url --push "origin" "$(VCS_REMOTE_PUSH_URL)"
# Fail fast if there's still no push access
	git push -o ci.skip --no-verify --tags "origin"
endif
ifneq ($(GITHUB_ACTIONS),true)
ifneq ($(PROJECT_GITHUB_PAT),)
# Also push to the mirror with the `ci.skip` option to avoid redundant runs on the
# mirror.
	git remote add "github" \
	    "https://$(PROJECT_GITHUB_PAT)@github.com/$(CI_PROJECT_PATH).git"
	git push -o ci.skip --no-verify --tags "github"
endif
endif
	set -x
endif
# Retrieve VCS data needed for versioning (tags) and release (release notes)
	ls -an "./.git/"
	git fetch --tags origin "$(TOWNCRIER_COMPARE_BRANCH)"
# Collect the versions involved in this release according to conventional commits
	cz_bump_args="--check-consistency --no-verify"
ifneq ($(VCS_BRANCH),master)
	cz_bump_args+=" --prerelease beta"
endif
ifeq ($(RELEASE_PUBLISH),true)
	cz_bump_args+=" --gpg-sign"
# Import the private signing key from CI secrets
	$(MAKE) -e ./var/log/gpg-import.log
endif
# Run first in case any input is needed from the developer
	exit_code=0
	$(TOX_EXEC_BUILD_ARGS) cz bump $${cz_bump_args} --dry-run || exit_code=$$?
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
	    $(TOX_EXEC_BUILD_ARGS) cz bump $${cz_bump_args} --dry-run |
	    sed -nE 's|.* *[Vv]ersion *(.+) *→ *(.+)|\2|p'
	)"
# Update the release notes/changelog
	docker compose run --rm python-project-structure-devel \
	    towncrier check --compare-with "origin/$(TOWNCRIER_COMPARE_BRANCH)"
	if ! git diff --cached --exit-code
	then
	    set +x
	    echo "CRITICAL: Cannot bump version with staged changes"
	    false
	fi
# Capture the release notes for *just this* release for creating the GitHub release.
# Have to run before the real `$ towncrier build` run without the `--draft` option
# because after that the `newsfragments` will have been deleted.
	docker compose run --rm python-project-structure-devel \
	    towncrier build --version "$${next_version}" --draft --yes \
	        >"./NEWS-release.rst"
# Build and stage the release notes to be commited by `$ cz bump`
	docker compose run --rm python-project-structure-devel \
	    towncrier build --version "$${next_version}" --yes
# Increment the version in VCS
	$(TOX_EXEC_BUILD_ARGS) cz bump $${cz_bump_args}
# Prevent uploading unintended distributions
	rm -vf ./dist/*
# Ensure the container image reflects the version bump but we don't need to update the
# requirements again.
	touch \
	    $(PYTHON_ENVS:%=./requirements/%/user.txt) \
	    $(PYTHON_ENVS:%=./requirements/%/devel.txt) \
	    $(PYTHON_ENVS:%=./requirements/%/host.txt)
	$(MAKE) -e "./var/docker/$(PYTHON_ENV)/log/build.log"

.PHONY: start
### Run the local development end-to-end stack services in the background as daemons
start: build-docker
	docker compose down
	docker compose up -d
.PHONY: run
### Run the local development end-to-end stack services in the foreground for debugging
run: build-docker
	docker compose down
	docker compose up

.PHONY: check-push
### Perform any checks that should only be run before pushing
check-push: build-docker
ifeq ($(RELEASE_PUBLISH),true)
	docker compose run --rm python-project-structure-devel \
	    towncrier check --compare-with "origin/develop"
endif

.PHONY: release
### Publish installable Python packages to PyPI and container images to Docker Hub
release: release-python
ifeq ($(GITLAB_CI),true)
	$(MAKE) -e release-docker
endif
.PHONY: release-python
### Publish installable Python packages to PyPI
release-python: \
		~/.pypirc ./var/log/codecov-install.log \
		./var/docker/$(PYTHON_ENV)/log/build.log \
		 ./var/log/host-install.log \
		./dist/.current.whl
# Upload any build or test artifacts to CI/CD providers
ifeq ($(GITLAB_CI),true)
	codecov --nonZero -t "$(CODECOV_TOKEN)" \
	    --file "./build/$(PYTHON_ENV)/coverage.xml"
endif
ifeq ($(RELEASE_PUBLISH),true)
# Import the private signing key from CI secrets
	$(MAKE) -e ./var/log/gpg-import.log
endif
# Build Python packages/distributions from the development Docker container for
# consistency/reproducibility.
	docker compose run --rm python-project-structure-devel pyproject-build -s
# https://twine.readthedocs.io/en/latest/#using-twine
	$(TOX_EXEC_BUILD_ARGS) twine check ./dist/python_project_structure-*
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
	$(TOX_EXEC_BUILD_ARGS) twine upload -s -r "$(PYPI_REPO)" \
	    ./dist/python_project_structure-*
# The VCS remote shouldn't reflect the release until the release has been successfully
# published
	git push -o ci.skip --no-verify --tags "origin" "HEAD:$(VCS_BRANCH)"
	current_version=$$(./.tox/build/bin/cz version --project)
# Create a GitLab release
	./.tox/build/bin/twine upload -s -r "gitlab" ./dist/python_project_structure-*
	release_cli_args="--description ./NEWS-release.rst"
	release_cli_args+=" --tag-name v$${current_version}"
	release_cli_args+=" --assets-link {\
	\"name\":\"PyPI\",\
	\"url\":\"https://$(PYPI_HOSTNAME)/project/$(CI_PROJECT_NAME)/$${current_version}/\",\
	\"link_type\":\"package\"\
	}"
	release_cli_args+=" --assets-link {\
	\"name\":\"GitLab-PyPI-Package-Registry\",\
	\"url\":\"$(CI_SERVER_URL)/$(CI_PROJECT_PATH)/-/packages/\",\
	\"link_type\":\"package\"\
	}"
	release_cli_args+=" --assets-link {\
	\"name\":\"Docker-Hub-Container-Registry\",\
	\"url\":\"https://hub.docker.com/r/merpatterson/$(CI_PROJECT_NAME)/tags\",\
	\"link_type\":\"image\"\
	}"
	docker compose run --rm gitlab-release-cli release-cli \
	    --server-url "$(CI_SERVER_URL)" --project-id "$(CI_PROJECT_ID)" \
	    create $${release_cli_args}
# Create a GitHub release
# Ensure the tag is in place on the GitHub mirror so we can create the project host
# release object:
	git push -o ci.skip --no-verify --tags "github"
	gh release create "v$${current_version}" $(GITHUB_RELEASE_ARGS) \
	    --notes-file "./NEWS-release.rst" ./dist/python_project_structure-*
endif
.PHONY: release-docker
### Publish container images to Docker Hub
release-docker: build-docker
# https://docs.docker.com/docker-hub/#step-5-build-and-push-a-container-image-to-docker-hub-from-your-computer
ifeq ($(CI),true)
	$(MAKE) -e "./var/log/docker-login.log" \
	    "./var/log/docker-login-gitlab.log" "./var/log/docker-login-github.log"
endif
	docker push "merpatterson/python-project-structure:$(VCS_BRANCH)"
	docker push "merpatterson/python-project-structure:devel-$(VCS_BRANCH)"
	docker push "merpatterson/python-project-structure:$(PYTHON_ENV)-$(VCS_BRANCH)"
	docker push "merpatterson/python-project-structure:$(PYTHON_ENV)-devel-$(VCS_BRANCH)"
	docker push "$(CI_REGISTRY_IMAGE):$(VCS_BRANCH)"
	docker push "$(CI_REGISTRY_IMAGE):devel-$(VCS_BRANCH)"
	docker push "ghcr.io/rpatterson/python-project-structure:$(VCS_BRANCH)"
	docker push "ghcr.io/rpatterson/python-project-structure:devel-$(VCS_BRANCH)"
ifeq ($(VCS_BRANCH),master)
# Only update tags end users may depend on to be stable from the `master` branch
	current_version=$$(
	    tox exec $(TOX_EXEC_OPTS) -e "build" -qq -- cz version --project
	)
	major_version=$$(echo $${current_version} | sed -nE 's|([0-9]+).*|\1|p')
	minor_version=$$(
	    echo $${current_version} | sed -nE 's|([0-9]+\.[0-9]+).*|\1|p'
	)
	docker push "merpatterson/python-project-structure:$${minor_version}"
	docker push "merpatterson/python-project-structure:$${major_version}"
	docker push "merpatterson/python-project-structure:latest"
	docker push "merpatterson/python-project-structure:devel"
	docker push "merpatterson/python-project-structure:$(PYTHON_ENV)-$${minor_version}"
	docker push "merpatterson/python-project-structure:$(PYTHON_ENV)-$${major_version}"
	docker push "merpatterson/python-project-structure:$(PYTHON_ENV)"
	docker push "merpatterson/python-project-structure:$(PYTHON_ENV)-devel"
	docker push "$(CI_REGISTRY_IMAGE):$${minor_version}"
	docker push "$(CI_REGISTRY_IMAGE):$${major_version}"
	docker push "$(CI_REGISTRY_IMAGE):latest"
	docker push "$(CI_REGISTRY_IMAGE):devel"
	docker push "$(CI_REGISTRY_IMAGE):$(PYTHON_ENV)-$${minor_version}"
	docker push "$(CI_REGISTRY_IMAGE):$(PYTHON_ENV)-$${major_version}"
	docker push "$(CI_REGISTRY_IMAGE):$(PYTHON_ENV)-latest"
	docker push "$(CI_REGISTRY_IMAGE):$(PYTHON_ENV)-devel"
	docker push "ghcr.io/rpatterson/python-project-structure:$${minor_version}"
	docker push "ghcr.io/rpatterson/python-project-structure:$${major_version}"
	docker push "ghcr.io/rpatterson/python-project-structure:latest"
	docker push "ghcr.io/rpatterson/python-project-structure:devel"
	docker push "ghcr.io/rpatterson/python-project-structure:$(PYTHON_ENV)-$${minor_version}"
	docker push "ghcr.io/rpatterson/python-project-structure:$(PYTHON_ENV)-$${major_version}"
	docker push "ghcr.io/rpatterson/python-project-structure:$(PYTHON_ENV)-latest"
	docker push "ghcr.io/rpatterson/python-project-structure:$(PYTHON_ENV)-devel"
	docker compose run --rm docker-pushrm
endif

.PHONY: format
### Automatically correct code in this checkout according to linters and style checkers
format: ./var/log/host-install.log
	$(TOX_EXEC_ARGS) autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables "./src/pythonprojectstructure/"
	$(TOX_EXEC_ARGS) autopep8 -v -i -r "./src/pythonprojectstructure/"
	$(TOX_EXEC_ARGS) black "./src/pythonprojectstructure/"

.PHONY: lint-docker
### Check the style and content of the `./Dockerfile*` files
lint-docker: ./.env
	docker compose run --rm hadolint hadolint "./Dockerfile"
	docker compose run --rm hadolint hadolint "./Dockerfile.devel"
	docker compose run --rm hadolint hadolint "./build-host/Dockerfile"

.PHONY: test
### Format the code and run the full suite of tests, coverage checks, and linters
test: lint-docker test-docker
.PHONY: test-docker
### Format the code and run the full suite of tests, coverage checks, and linters
test-docker: ./.env build-wheel
	$(MAKE) -e -j \
	    TOX_RUN_ARGS="run --installpkg ./dist/$$(
	        readlink "./dist/.current.whl"
	    )" \
	    DOCKER_BUILD_ARGS="--progress plain" \
	    $(PYTHON_MINORS:%=test-docker-%)
.PHONY: $(PYTHON_MINORS:%=test-docker-%)
### Run the full suite of tests inside a docker container for this Python version
$(PYTHON_MINORS:%=test-docker-%):
	$(MAKE) -e PYTHON_MINORS="$(@:test-docker-%=%)" \
	    PYTHON_ENV="py$(subst .,,$(@:test-docker-%=%))" test-docker-pyminor
.PHONY: test-docker-pyminor
test-docker-pyminor: build-docker-$(PYTHON_MINOR)
	docker_run_args="--rm"
	if [ ! -t 0 ]
	then
# No fancy output when running in parallel
	    docker_run_args+=" -T"
	fi
# Ensure the dist/package has been correctly installed in the image
	docker compose run $${docker_run_args} python-project-structure \
	    python -m pythonprojectstructure --help
	docker compose run $${docker_run_args} python-project-structure \
	    python-project-structure --help
# Run from the development Docker container for consistency
	docker compose run $${docker_run_args} python-project-structure-devel \
	    make -e PYTHON_MINORS="$(PYTHON_MINORS)" TOX_RUN_ARGS="$(TOX_RUN_ARGS)" \
	        test-local
.PHONY: test-local
### Run the full suite of tests on the local host
test-local:
	tox $(TOX_RUN_ARGS) -e "$(TOX_ENV_LIST)"
.PHONY: test-debug
### Run tests in the main/default environment and invoke the debugger on errors/failures
test-debug: ./.tox/$(PYTHON_ENV)/log/editable.log
	$(TOX_EXEC_ARGS) pytest --pdb

.PHONY: upgrade
### Update all fixed/pinned dependencies to their latest available versions
upgrade:
	touch "./setup.cfg" "./requirements/build.txt.in" "./requirements/host.txt.in"
	$(MAKE) -e PUID=$(PUID) "build-docker"
# Update VCS hooks from remotes to the latest tag.
	$(TOX_EXEC_BUILD_ARGS) pre-commit autoupdate

# TEMPLATE: Run this once for your project.  See the `./var/log/docker-login*.log`
# targets for the authentication environment variables that need to be set or just login
# to those container registries manually and touch these targets.
.PHONY: bootstrap-project
### Run any tasks needed to be run once for a given project by a maintainer
bootstrap-project: \
		./var/log/docker-login-gitlab.log \
		./var/log/docker-login-github.log
# Initially seed the build host Docker image to bootstrap CI/CD environments
# GitLab CI/CD:
	$(MAKE) -C "./build-host/" \
	    CI_REGISTRY_IMAGE="registry.gitlab.com/rpatterson/python-project-structure"\
	    release
# GitHub Actions:
	$(MAKE) -C "./build-host/" \
	    CI_REGISTRY_IMAGE="ghcr.io/rpatterson/python-project-structure" release

.PHONY: clean
### Restore the checkout to a state as close to an initial clone as possible
clean:
	docker compose down --remove-orphans --rmi "all" -v || true
	$(TOX_EXEC_BUILD_ARGS) pre-commit uninstall \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push" \
	    || true
	$(TOX_EXEC_BUILD_ARGS) pre-commit clean || true
	git clean -dfx -e "var/" -e ".env"
	rm -rfv "./var/log/"
	rm -rf "./var/docker/"


## Utility targets

.PHONY: expand-template
## Create a file from a template replacing environment variables
expand-template: ./var/log/host-install.log
	set +x
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
$(PYTHON_ENVS:%=./requirements/%/devel.txt): ./pyproject.toml ./setup.cfg ./tox.ini
	true DEBUG Updated prereqs: $(?)
	$(MAKE) ./var/log/host-install.log
	tox exec $(TOX_EXEC_OPTS) -e "$(@:requirements/%/devel.txt=%)" -- \
	    pip-compile --resolver "backtracking" $(PIP_COMPILE_ARGS) --extra "devel" \
	    --output-file "$(@)" "$(<)"
	mkdir -pv "./var/log/"
	touch "./var/log/rebuild.log"
$(PYTHON_ENVS:%=./requirements/%/user.txt): ./pyproject.toml ./setup.cfg ./tox.ini
	true DEBUG Updated prereqs: $(?)
	$(MAKE) ./var/log/host-install.log
	tox exec $(TOX_EXEC_OPTS) -e "$(@:requirements/%/user.txt=%)" -- \
	    pip-compile --resolver "backtracking" $(PIP_COMPILE_ARGS) --output-file "$(@)" "$(<)"
	mkdir -pv "./var/log/"
	touch "./var/log/rebuild.log"
$(PYTHON_ENVS:%=./requirements/%/host.txt): ./requirements/host.txt.in
	true DEBUG Updated prereqs: $(?)
	$(MAKE) ./var/log/host-install.log
	tox exec $(TOX_EXEC_OPTS) -e "$(@:requirements/%/host.txt=%)" -- \
	    pip-compile --resolver "backtracking" $(PIP_COMPILE_ARGS) --output-file "$(@)" "$(<)"
# Only update the installed tox version for the latest/host/main/default Python version
	if [ "$(@:requirements/%/host.txt=%)" = "$(PYTHON_ENV)" ]
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
	mkdir -pv "./var/log/"
	touch "./var/log/rebuild.log"
$(PYTHON_ENVS:%=./requirements/%/build.txt): ./requirements/build.txt.in
	true DEBUG Updated prereqs: $(?)
	$(MAKE) ./var/log/host-install.log
	tox exec $(TOX_EXEC_OPTS) -e "$(@:requirements/%/build.txt=%)" -- \
	    pip-compile --resolver "backtracking" $(PIP_COMPILE_ARGS) --output-file "$(@)" "$(<)"

# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`
$(PYTHON_ENVS:%=./.tox/%/log/editable.log):
	$(MAKE) ./var/log/host-install.log
	mkdir -pv "$(dir $(@))"
	tox exec $(TOX_EXEC_OPTS) -e "$(@:./.tox/%/log/editable.log=%)" -- \
	    pip install -e "./" | tee -a "$(@)"

# Build a wheel package but only if one hasn't already been made
./dist/.current.whl:
	$(MAKE) build-wheel

# Docker targets
./var/docker/$(PYTHON_ENV)/log/build.log: \
		./Dockerfile ./Dockerfile.devel ./.dockerignore ./bin/entrypoint \
		./pyproject.toml ./setup.cfg ./tox.ini ./requirements/host.txt.in \
		./docker-compose.yml ./docker-compose.override.yml ./.env \
		./var/docker/$(PYTHON_ENV)/log/rebuild.log
	true DEBUG Updated prereqs: $(?)
# Ensure access permissions to build artifacts in container volumes.
# If created by `# dockerd`, they end up owned by `root`.
	mkdir -pv "$(dir $(@))" \
	    "./src/python_project_structure.egg-info/" \
	    "./var/docker/$(PYTHON_ENV)/python_project_structure.egg-info/" \
	    "./.tox/" "./var/docker/$(PYTHON_ENV)/.tox/"
# Workaround issues with local images and the development image depending on the end
# user image.  It seems that `depends_on` isn't sufficient.
	$(MAKE) ./var/log/host-install.log
	current_version=$$(
	    tox exec $(TOX_EXEC_OPTS) -e "build" -qq -- cz version --project
	)
# https://github.com/moby/moby/issues/39003#issuecomment-879441675
	docker_build_args="$(DOCKER_BUILD_ARGS) \
	    --build-arg BUILDKIT_INLINE_CACHE=1 \
	    --build-arg PYTHON_MINOR=$(PYTHON_MINOR) \
	    --build-arg PYTHON_ENV=$(PYTHON_ENV) \
	    --build-arg VERSION=$${current_version}"
	docker_build_user_tags=" \
	    --tag merpatterson/python-project-structure:local \
	    --tag merpatterson/python-project-structure:$(VCS_BRANCH) \
	    --tag merpatterson/python-project-structure:$${current_version} \
	    --tag merpatterson/python-project-structure:$(PYTHON_ENV)-local \
	    --tag merpatterson/python-project-structure:$(PYTHON_ENV)-$(VCS_BRANCH) \
	    --tag merpatterson/python-project-structure:$(PYTHON_ENV)-$${current_version} \
	    --tag $(CI_REGISTRY_IMAGE):$(VCS_BRANCH) \
	    --tag $(CI_REGISTRY_IMAGE):$${current_version} \
	    --tag $(CI_REGISTRY_IMAGE):$(PYTHON_ENV)-$(VCS_BRANCH) \
	    --tag $(CI_REGISTRY_IMAGE):$(PYTHON_ENV)-$${current_version} \
	    --tag ghcr.io/rpatterson/python-project-structure:$(VCS_BRANCH) \
	    --tag ghcr.io/rpatterson/python-project-structure:$${current_version} \
	    --tag ghcr.io/rpatterson/python-project-structure:$(PYTHON_ENV)-$(VCS_BRANCH) \
	    --tag ghcr.io/rpatterson/python-project-structure:$(PYTHON_ENV)-$${current_version}"
ifeq ($(VCS_BRANCH),master)
# Only update tags end users may depend on to be stable from the `master` branch
	major_version=$$(echo $${current_version} | sed -nE 's|([0-9]+).*|\1|p')
	minor_version=$$(
	    echo $${current_version} | sed -nE 's|([0-9]+\.[0-9]+).*|\1|p'
	)
	docker_build_user_tags+=" \
	    --tag merpatterson/python-project-structure:$${minor_version} \
	    --tag merpatterson/python-project-structure:$${major_version} \
	    --tag merpatterson/python-project-structure:latest \
	    --tag merpatterson/python-project-structure:$(PYTHON_ENV)-$${minor_version} \
	    --tag merpatterson/python-project-structure:$(PYTHON_ENV)-$${major_version} \
	    --tag merpatterson/python-project-structure:$(PYTHON_ENV) \
	    --tag $(CI_REGISTRY_IMAGE):$${minor_version} \
	    --tag $(CI_REGISTRY_IMAGE):$${major_version} \
	    --tag $(CI_REGISTRY_IMAGE):latest \
	    --tag $(CI_REGISTRY_IMAGE):$(PYTHON_ENV)-$${minor_version} \
	    --tag $(CI_REGISTRY_IMAGE):$(PYTHON_ENV)-$${major_version} \
	    --tag $(CI_REGISTRY_IMAGE):$(PYTHON_ENV)-latest \
	    --tag ghcr.io/rpatterson/python-project-structure:$${minor_version} \
	    --tag ghcr.io/rpatterson/python-project-structure:$${major_version} \
	    --tag ghcr.io/rpatterson/python-project-structure:latest \
	    --tag ghcr.io/rpatterson/python-project-structure:$(PYTHON_ENV)-$${minor_version} \
	    --tag ghcr.io/rpatterson/python-project-structure:$(PYTHON_ENV)-$${major_version} \
	    --tag ghcr.io/rpatterson/python-project-structure:$(PYTHON_ENV)-latest"
endif
	docker_build_caches=""
ifeq ($(GITLAB_CI),true)
# Don't cache when building final releases on `master`
ifneq ($(VCS_BRANCH),master)
	docker pull "$(CI_REGISTRY_IMAGE):$(PYTHON_ENV)-$(VCS_BRANCH)" || true
	docker_build_caches+=" --cache-from $(CI_REGISTRY_IMAGE):$(PYTHON_ENV)-$(VCS_BRANCH)"
endif
endif
ifeq ($(GITHUB_ACTIONS),true)
ifneq ($(VCS_BRANCH),master)
# Can't use the GitHub Actions cache when we're only pushing images from GitLab CI/CD
	docker pull "ghcr.io/rpatterson/python-project-structure:$(PYTHON_ENV)-$(VCS_BRANCH)" || true
	docker_build_caches+=" --cache-from \
	    ghcr.io/rpatterson/python-project-structure:$(PYTHON_ENV)-$(VCS_BRANCH)"
endif
endif
	docker buildx build --pull $${docker_build_args} $${docker_build_user_tags} \
	    $${docker_build_caches} "./"
# Ensure any subsequent builds have optimal caches
ifeq ($(GITLAB_CI),true)
	$(MAKE) -e ./var/log/docker-login-gitlab.log
	docker push "$(CI_REGISTRY_IMAGE):$(PYTHON_ENV)-$(VCS_BRANCH)"
endif
ifeq ($(GITHUB_ACTIONS),true)
	$(MAKE) -e ./var/log/docker-login-github.log
	docker push "ghcr.io/rpatterson/python-project-structure:$(PYTHON_ENV)-$(VCS_BRANCH)"
endif
# Build the development image
	docker_build_caches=""
ifeq ($(GITLAB_CI),true)
ifneq ($(VCS_BRANCH),master)
	docker pull "$(CI_REGISTRY_IMAGE):devel-$(VCS_BRANCH)" || true
	docker_build_caches+=" --cache-from $(CI_REGISTRY_IMAGE):devel-$(VCS_BRANCH)"
endif
endif
ifeq ($(GITHUB_ACTIONS),true)
ifneq ($(VCS_BRANCH),master)
	docker pull "ghcr.io/rpatterson/python-project-structure:devel-$(VCS_BRANCH)" || true
	docker_build_caches+=" --cache-from \
	    ghcr.io/rpatterson/python-project-structure:devel-$(VCS_BRANCH)"
endif
endif
	docker_build_devel_tags=" \
	    --tag merpatterson/python-project-structure:devel-local \
	    --tag merpatterson/python-project-structure:devel-$(VCS_BRANCH) \
	    --tag merpatterson/python-project-structure:$(PYTHON_ENV)-devel-local \
	    --tag merpatterson/python-project-structure:$(PYTHON_ENV)-devel-$(VCS_BRANCH) \
	    --tag $(CI_REGISTRY_IMAGE):devel-$(VCS_BRANCH) \
	    --tag $(CI_REGISTRY_IMAGE):$(PYTHON_ENV)-devel-$(VCS_BRANCH) \
	    --tag ghcr.io/rpatterson/python-project-structure:devel-$(VCS_BRANCH) \
	    --tag ghcr.io/rpatterson/python-project-structure:$(PYTHON_ENV)-devel-$(VCS_BRANCH)"
ifeq ($(VCS_BRANCH),master)
	docker_build_devel_tags+=" \
	    --tag merpatterson/python-project-structure:devel \
	    --tag merpatterson/python-project-structure:$(PYTHON_ENV)-devel \
	    --tag $(CI_REGISTRY_IMAGE):devel \
	    --tag $(CI_REGISTRY_IMAGE):$(PYTHON_ENV)-devel \
	    --tag ghcr.io/rpatterson/python-project-structure:devel \
	    --tag ghcr.io/rpatterson/python-project-structure:$(PYTHON_ENV)-devel"
endif
	docker buildx build $${docker_build_args} $${docker_build_devel_tags} \
	    $${docker_build_caches} --file "./Dockerfile.devel" "./"
# Ensure any subsequent builds have optimal caches
ifeq ($(GITLAB_CI),true)
	docker push "$(CI_REGISTRY_IMAGE):$(PYTHON_ENV)-devel-$(VCS_BRANCH)"
endif
ifeq ($(GITHUB_ACTIONS),true)
	docker push "ghcr.io/rpatterson/python-project-structure:$(PYTHON_ENV)-devel-$(VCS_BRANCH)"
endif
	date >>"$(@)"
# The image installs the host requirements, reflect that in the bind mount volumes
	date >>"$(@:%/build.log=%/host-install.log)"
# Update the pinned/frozen versions, if needed, using the container.  If changed, then
# we may need to re-build the container image again to ensure it's current and correct.
	docker compose run --rm -T python-project-structure-devel \
	    make -e PYTHON_MINORS="$(PYTHON_MINOR)" build-requirements-$(PYTHON_ENV)
	$(MAKE) -e "$(@)"
# Marker file used to trigger the rebuild of the image for just one Python version.
# Useful to workaround async timestamp issues when running jobs in parallel.
./var/docker/$(PYTHON_ENV)/log/rebuild.log:
	mkdir -pv "$(dir $(@))"
	date >>"$(@)"

# Local environment variables from a template
./.env: ./.env.in
	$(MAKE) -e "template=$(<)" "target=$(@)" expand-template

# Perform any one-time local checkout set up
./var/log/host-install.log:
	mkdir -pv "$(dir $(@))"
# Bootstrap the minimum Python environment
	(
	    if ! which pip
	    then
	        if which apk
	        then
	            sudo apk update
	            sudo apk add "gettext" "py3-pip" "gnupg" "github-cli" "curl"
	        elif which apt-get
	        then
	            sudo apt-get update
	            sudo apt-get install -y \
	                "gettext-base" "python3-pip" "gnupg" "gh" "curl"
	        else
	            set +x
	            echo "ERROR: OS not supported for installing host dependencies"
	            false
	        fi
	    fi
	    if [ -e ./requirements/$(PYTHON_HOST_ENV)/host.txt ]
	    then
	        pip install -r "./requirements/$(PYTHON_HOST_ENV)/host.txt"
	    else
	        pip install -r "./requirements/host.txt.in"
	    fi
	) | tee -a "$(@)"

./var/log/codecov-install.log:
	mkdir -pv "$(dir $(@))"
# Install the code test coverage publishing tool
	(
	    if ! which codecov
	    then
	        mkdir -pv ~/.local/bin/
# https://docs.codecov.com/docs/codecov-uploader#using-the-uploader-with-codecovio-cloud
	        if which brew
	        then
# Mac OS X
	            curl --output-dir ~/.local/bin/ -Os \
	                "https://uploader.codecov.io/latest/macos/codecov"
	        elif which apk
	        then
# Alpine
	            wget --directory-prefix ~/.local/bin/ \
	                "https://uploader.codecov.io/latest/alpine/codecov"
	        else
# Other Linux distributions
	            curl --output-dir ~/.local/bin/ -Os \
	                "https://uploader.codecov.io/latest/linux/codecov"
	        fi
	        chmod +x ~/.local/bin/codecov
	    fi
	    if ! which codecov
	    then
	        set +x
	        echo "ERROR: CodeCov CLI tool still not on PATH"
	        false
	    fi
	) | tee -a "$(@)"

./.git/hooks/pre-commit:
	$(MAKE) ./var/log/host-install.log
	$(TOX_EXEC_BUILD_ARGS) pre-commit install \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push"

# Capture any project initialization tasks for reference.  Not actually usable.
./pyproject.toml:
	$(MAKE) ./var/log/host-install.log
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

./var/log/docker-login.log: ./.env
	mkdir -pv "$(dir $(@))"
	set +x
	source "./.env"
	printenv "DOCKER_PASS" | docker login -u "merpatterson" --password-stdin
	date | tee -a "$(@)"
./var/log/docker-login-gitlab.log:
	mkdir -pv "$(dir $(@))"
	set +x
	printenv "CI_REGISTRY_PASSWORD" |
	    docker login -u "$(CI_REGISTRY_USER)" --password-stdin "$(CI_REGISTRY)"
	date | tee -a "$(@)"
./var/log/docker-login-github.log:
	mkdir -pv "$(dir $(@))"
	set +x
	printenv "PROJECT_GITHUB_PAT" |
	    docker login -u "$(GITHUB_REPOSITORY_OWNER)" --password-stdin "ghcr.io"
	date | tee -a "$(@)"

# GPG signing key creation and management in CI
export GPG_PASSPHRASE=
./var/ci-cd-signing-subkey.asc:
# We need a private key in the CI/CD environment for signing release commits and
# artifacts.  Use a subkey so that it can be revoked without affecting your main key.
# This recipe captures what I had to do to export a private signing subkey.  It's not
# widely tested so it should probably only be used for reference.  It worked for me but
# the risk is leaking your main private key so double and triple check all your
# assumptions and results.
# 1. Create a signing subkey with a NEW, SEPARATE passphrase:
#    https://wiki.debian.org/Subkeys#How.3F
# 2. Get the long key ID for that private subkey:
#	gpg --list-secret-keys --keyid-format "LONG"
# 3. Export *just* that private subkey and verify that the main secret key packet is the
#    GPG dummy packet and that the only other private key included is the intended
#    subkey:
#	gpg --armor --export-secret-subkeys "$(GPG_SIGNING_KEYID)!" |
#	    gpg --list-packets
# 4. Export that key as text to a file:
	gpg --armor --export-secret-subkeys "$(GPG_SIGNING_KEYID)!" >"$(@)"
# 5. Confirm that the exported key can be imported into a temporary GNU PG directory and
#    that temporary directory can then be used to sign files:
#	gnupg_homedir=$$(mktemp -d --suffix=".d" "gnupd.XXXXXXXXXX")
#	printenv 'GPG_PASSPHRASE' >"$${gnupg_homedir}/.passphrase"
#	gpg --homedir "$${gnupg_homedir}" --batch --import <"$(@)"
#	echo "Test signature content" >"$${gnupg_homedir}/test-sig.txt"
#	gpgconf --kill gpg-agent
#	gpg --homedir "$${gnupg_homedir}" --batch --pinentry-mode "loopback" \
#	    --passphrase-file "$${gnupg_homedir}/.passphrase" \
#	    --local-user "$(GPG_SIGNING_KEYID)!" --sign "$${gnupg_homedir}/test-sig.txt"
#	gpg --batch --verify "$${gnupg_homedir}/test-sig.txt.gpg"
# 6. Add the contents of this target as a `GPG_SIGNING_PRIVATE_KEY` secret in CI and the
# passphrase for the signing subkey as a `GPG_PASSPHRASE` secret in CI
./var/log/gpg-import.log:
# In each CI run, import the private signing key from the CI secrets
	printenv "GPG_SIGNING_PRIVATE_KEY" | gpg --batch --import | tee -a "$(@)"
	echo 'default-key:0:"$(GPG_SIGNING_KEYID)' | gpgconf —change-options gpg
	git config --global user.signingkey "$(GPG_SIGNING_KEYID)"
# "Unlock" the signing key for the remainder of this CI run:
	printenv 'GPG_PASSPHRASE' >"./var/ci-cd-signing-subkey.passphrase"
	true | gpg --batch --pinentry-mode "loopback" \
	    --passphrase-file "./var/ci-cd-signing-subkey.passphrase" \
	    --sign | gpg --list-packets
