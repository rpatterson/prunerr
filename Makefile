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
# Project-specific variables
export DOCKER_USER=merpatterson
# TEMPLATE: See comments towards the bottom and update.
GPG_SIGNING_KEYID=2EFF7CCE6828E359
CI_UPSTREAM_NAMESPACE=rpatterson
CI_PROJECT_NAME=python-project-structure


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
USER_EMAIL:=$(USER_NAME)@$(shell hostname -f)
export PUID:=$(shell id -u)
export PGID:=$(shell id -g)
export CHECKOUT_DIR=$(PWD)
TZ=Etc/UTC
ifneq ("$(wildcard /usr/share/zoneinfo/)","")
TZ=$(shell \
  realpath --relative-to=/usr/share/zoneinfo/ \
  $(firstword $(realpath /private/etc/localtime /etc/localtime)) \
)
endif
export TZ
export DOCKER_GID=$(shell getent group "docker" | cut -d ":" -f 3)

# Values concerning supported Python versions:
# Use the same Python version tox would as a default.
# https://tox.wiki/en/latest/config.html#base_python
PYTHON_HOST_MINOR:=$(shell \
    pip --version | sed -nE 's|.* \(python ([0-9]+.[0-9]+)\)$$|\1|p;q')
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
export PYTHON_MINOR=$(firstword $(PYTHON_MINORS))
else ifeq ($(findstring $(PYTHON_MINOR),$(PYTHON_MINORS)),)
export PYTHON_MINOR=$(firstword $(PYTHON_MINORS))
endif
export PYTHON_MINOR
export PYTHON_ENV=py$(subst .,,$(PYTHON_MINOR))
PYTHON_SHORT_MINORS=$(subst .,,$(PYTHON_MINORS))
PYTHON_ENVS=$(PYTHON_SHORT_MINORS:%=py%)
PYTHON_ALL_ENVS=$(PYTHON_ENVS) build
export PYTHON_WHEEL=

# Values derived from VCS/git:
VCS_LOCAL_BRANCH:=$(shell git branch --show-current)
CI_COMMIT_BRANCH=
GITHUB_REF_TYPE=
GITHUB_REF_NAME=
ifeq ($(VCS_LOCAL_BRANCH),)
ifneq ($(CI_COMMIT_BRANCH),)
VCS_LOCAL_BRANCH=$(CI_COMMIT_BRANCH)
else ifeq ($(GITHUB_REF_TYPE),branch)
VCS_LOCAL_BRANCH=$(GITHUB_REF_NAME)
endif
endif
VCS_TAG=
CI_COMMIT_TAG=
ifeq ($(VCS_TAG),)
ifneq ($(CI_COMMIT_TAG),)
VCS_TAG=$(CI_COMMIT_TAG)
else ifeq ($(GITHUB_REF_TYPE),tag)
VCS_TAG=$(GITHUB_REF_NAME)
endif
endif
ifeq ($(VCS_LOCAL_BRANCH),)
# Guess branch name from tag:
ifneq ($(shell echo "$(VCS_TAG)" | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$$'),)
# Final release, should be from main:
VCS_LOCAL_BRANCH=main
else ifneq ($(shell echo "$(VCS_TAG)" | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+.+$$'),)
# Pre-release, should be from develop:
VCS_LOCAL_BRANCH=develop
endif
endif
# Reproduce what we need of git's branch and remote configuration and logic:
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
# Determine the best remote and branch for versioning data, e.g. `v*` tags:
VCS_REMOTE=$(VCS_PUSH_REMOTE)
VCS_BRANCH=$(VCS_LOCAL_BRANCH)
export VCS_BRANCH
# Determine the best remote and branch for release data, e.g. conventional commits:
VCS_COMPARE_REMOTE=$(VCS_UPSTREAM_REMOTE)
ifeq ($(VCS_COMPARE_REMOTE),)
VCS_COMPARE_REMOTE=$(VCS_PUSH_REMOTE)
endif
VCS_COMPARE_BRANCH=$(VCS_UPSTREAM_BRANCH)
ifeq ($(VCS_COMPARE_BRANCH),)
VCS_COMPARE_BRANCH=$(VCS_BRANCH)
endif
# Under CI, check commits and release notes against the branch to be merged into:
CI=false
ifeq ($(CI),true)
ifeq ($(VCS_COMPARE_BRANCH),develop)
VCS_COMPARE_BRANCH=main
else ifneq ($(VCS_BRANCH),main)
VCS_COMPARE_BRANCH=develop
endif
# If pushing to upstream release branches, get release data compared to the previous
# release:
else ifeq ($(VCS_COMPARE_BRANCH),develop)
VCS_COMPARE_BRANCH=main
endif
VCS_BRANCH_SUFFIX=upgrade
VCS_MERGE_BRANCH=$(VCS_BRANCH:%-$(VCS_BRANCH_SUFFIX)=%)
# Assemble the targets used to avoid redundant fetches during release tasks:
VCS_FETCH_TARGETS=./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH)
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
# Determine the sequence of branches to find closes existing build artifacts, such as
# docker images:
VCS_BRANCHES=$(VCS_BRANCH)
ifneq ($(VCS_BRANCH),main)
ifneq ($(VCS_BRANCH),develop)
VCS_BRANCHES+=develop
endif
VCS_BRANCHES+=main
endif

# Values used to run Tox:
TOX_ENV_LIST=$(subst $(EMPTY) ,$(COMMA),$(PYTHON_ENVS))
ifeq ($(words $(PYTHON_MINORS)),1)
TOX_RUN_ARGS=run
else
TOX_RUN_ARGS=run-parallel --parallel auto --parallel-live
endif
ifneq ($(PYTHON_WHEEL),)
TOX_RUN_ARGS+= --installpkg "$(PYTHON_WHEEL)"
endif
export TOX_RUN_ARGS
# The options that allow for rapid execution of arbitrary commands in the venvs managed
# by tox
TOX_EXEC_OPTS=--no-recreate-pkg --skip-pkg-install
TOX_EXEC_ARGS=tox exec $(TOX_EXEC_OPTS) -e "$(PYTHON_ENV)" --
TOX_EXEC_BUILD_ARGS=tox exec $(TOX_EXEC_OPTS) -e "build" --

# Values used to build Docker images:
DOCKER_FILE=./Dockerfile
DOCKER_BUILD_ARGS=--output "type=docker"
export DOCKER_BUILD_PULL=false
# Values used to tag built images:
export DOCKER_VARIANT=
DOCKER_VARIANT_PREFIX=
ifneq ($(DOCKER_VARIANT),)
DOCKER_VARIANT_PREFIX=$(DOCKER_VARIANT)-
endif
export DOCKER_BRANCH_TAG=$(subst /,-,$(VCS_BRANCH))
GITLAB_CI=false
GITHUB_ACTIONS=false
CI_PROJECT_NAMESPACE=$(CI_UPSTREAM_NAMESPACE)
CI_TEMPLATE_REGISTRY_HOST=registry.gitlab.com
ifeq ($(GITHUB_ACTIONS),true)
DOCKER_REGISTRY_HOST=ghcr.io
else
DOCKER_REGISTRY_HOST=$(CI_TEMPLATE_REGISTRY_HOST)
endif
export DOCKER_REGISTRY_HOST
CI_REGISTRY=$(CI_TEMPLATE_REGISTRY_HOST)/$(CI_PROJECT_NAMESPACE)
CI_REGISTRY_IMAGE=$(CI_REGISTRY)/$(CI_PROJECT_NAME)
DOCKER_REGISTRIES=DOCKER GITLAB GITHUB
export DOCKER_REGISTRY=$(firstword $(DOCKER_REGISTRIES))
DOCKER_IMAGE_DOCKER=$(DOCKER_USER)/$(CI_PROJECT_NAME)
DOCKER_IMAGE_GITLAB=$(CI_REGISTRY_IMAGE)
DOCKER_IMAGE_GITHUB=ghcr.io/$(CI_PROJECT_NAMESPACE)/$(CI_PROJECT_NAME)
DOCKER_IMAGE=$(DOCKER_IMAGE_$(DOCKER_REGISTRY))
DOCKER_IMAGES=
ifeq ($(GITLAB_CI),true)
DOCKER_IMAGES+=$(DOCKER_IMAGE_GITLAB)
else ifeq ($(GITHUB_ACTIONS),true)
DOCKER_IMAGES+=$(DOCKER_IMAGE_GITHUB)
else
DOCKER_IMAGES+=$(DOCKER_IMAGE_DOCKER)
endif
# Values used to run built images in containers:
DOCKER_VOLUMES=\
./var/docker/$(PYTHON_ENV)/ \
./src/python_project_structure.egg-info/ \
./var/docker/$(PYTHON_ENV)/python_project_structure.egg-info/ \
./.tox/ ./var/docker/$(PYTHON_ENV)/.tox/
DOCKER_COMPOSE_RUN_ARGS=
DOCKER_COMPOSE_RUN_ARGS+= --rm
ifeq ($(shell tty),not a tty)
DOCKER_COMPOSE_RUN_ARGS+= -T
endif

# Values derived from or overridden by CI environments:
GITHUB_REPOSITORY_OWNER=$(CI_UPSTREAM_NAMESPACE)
# Determine if this checkout is a fork of the upstream project:
CI_IS_FORK=false
ifeq ($(GITLAB_CI),true)
USER_EMAIL=$(USER_NAME)@runners-manager.gitlab.com
ifneq ($(VCS_BRANCH),develop)
ifneq ($(VCS_BRANCH),main)
DOCKER_REGISTRIES=GITLAB
endif
endif
ifneq ($(CI_PROJECT_NAMESPACE),$(CI_UPSTREAM_NAMESPACE))
CI_IS_FORK=true
DOCKER_REGISTRIES=GITLAB
DOCKER_IMAGES+=$(DOCKER_REGISTRY_HOST)/$(CI_UPSTREAM_NAMESPACE)/$(CI_PROJECT_NAME)
endif
else ifeq ($(GITHUB_ACTIONS),true)
USER_EMAIL=$(USER_NAME)@actions.github.com
ifneq ($(VCS_BRANCH),develop)
ifneq ($(VCS_BRANCH),main)
DOCKER_REGISTRIES=GITHUB
endif
endif
ifneq ($(GITHUB_REPOSITORY_OWNER),$(CI_UPSTREAM_NAMESPACE))
CI_IS_FORK=true
DOCKER_REGISTRIES=GITHUB
DOCKER_IMAGES+=ghcr.io/$(GITHUB_REPOSITORY_OWNER)/$(CI_PROJECT_NAME)
endif
endif
# Take GitHub auth from env under GitHub actions but from secrets on other hosts:
GITHUB_TOKEN=
PROJECT_GITHUB_PAT=
ifeq ($(GITHUB_TOKEN),)
GITHUB_TOKEN=$(PROJECT_GITHUB_PAT)
else ifeq ($(PROJECT_GITHUB_PAT),)
PROJECT_GITHUB_PAT=$(GITHUB_TOKEN)
endif
GH_TOKEN=$(GITHUB_TOKEN)
export GH_TOKEN
export GITHUB_TOKEN
export PROJECT_GITHUB_PAT

# Values used for publishing releases:
# Safe defaults for testing the release process without publishing to the final/official
# hosts/indexes/registries:
PIP_COMPILE_ARGS=--upgrade
RELEASE_PUBLISH=false
PYPI_REPO=testpypi
PYPI_HOSTNAME=test.pypi.org
DOCKER_BUILD_ARGS=
# Only publish releases from the `main` or `develop` branches:
ifeq ($(CI),true)
# Compile requirements on CI/CD as a check to make sure all changes to dependencies have
# been reflected in the frozen/pinned versions, but don't upgrade packages so that
# external changes, such as new PyPI releases, don't turn CI/CD red spuriously and
# unrelated to the contributor's actual changes.
PIP_COMPILE_ARGS=
endif
GITHUB_RELEASE_ARGS=--prerelease
# Only publish releases from the `main` or `develop` branches and only under the
# canonical CI/CD platform:
ifeq ($(GITLAB_CI),true)
ifeq ($(VCS_BRANCH),main)
RELEASE_PUBLISH=true
GITHUB_RELEASE_ARGS=
else ifeq ($(VCS_BRANCH),develop)
# Publish pre-releases from the `develop` branch:
RELEASE_PUBLISH=true
endif
ifeq ($(RELEASE_PUBLISH),true)
PYPI_REPO=pypi
PYPI_HOSTNAME=pypi.org
ifeq ($(PYTHON_MINOR),$(PYTHON_HOST_MINOR))
# Only build and publish multi-platform images for the canonical Python version:
# TEMPLATE: Choose the platforms on which your end-users need to be able to run the
# image.  These default platforms should cover most common end-user platforms, including
# modern Apple M1 CPUs, Raspberry Pi devices, etc.:
DOCKER_PLATFORMS=linux/amd64 linux/arm64 linux/arm/v7
endif
endif
endif
CI_REGISTRY_USER=$(CI_PROJECT_NAMESPACE)
# Address undefined variables warnings when running under local development
PYPI_PASSWORD=
export PYPI_PASSWORD
TEST_PYPI_PASSWORD=
export TEST_PYPI_PASSWORD
VCS_REMOTE_PUSH_URL=
CODECOV_TOKEN=
DOCKER_PASS=
export DOCKER_PASS
CI_PROJECT_ID=
export CI_PROJECT_ID
CI_JOB_TOKEN=
export CI_JOB_TOKEN
CI_REGISTRY_PASSWORD=
export CI_REGISTRY_PASSWORD
GH_TOKEN=

# Done with `$(shell ...)`, echo recipe commands going forward
.SHELLFLAGS+= -x


## Makefile "functions":
#
# Snippets whose output is frequently used including across recipes.  Used for output
# only, not actually making any changes.
# https://www.gnu.org/software/make/manual/html_node/Call-Function.html

# Return the most recently built package:
current_pkg = $(shell ls -t ./dist/*$(1) | head -n 1)


## Top-level targets:

.PHONY: all
### The default target.
all: build

.PHONY: start
### Run the local development end-to-end stack services in the background as daemons.
start: build-docker-volumes-$(PYTHON_ENV) build-docker-$(PYTHON_MINOR) ./.env
	docker compose down
	docker compose up -d

.PHONY: run
### Run the local development end-to-end stack services in the foreground for debugging.
run: build-docker-volumes-$(PYTHON_ENV) build-docker-$(PYTHON_MINOR) ./.env
	docker compose down
	docker compose up


## Build Targets:
#
# Recipes that make artifacts needed for by end-users, development tasks, other recipes.

.PHONY: build
### Set up everything for development from a checkout, local and in containers.
build: ./.git/hooks/pre-commit \
		$(HOME)/.local/var/log/python-project-structure-host-install.log \
		build-docker

.PHONY: build-pkgs
### Ensure the built package is current when used outside of tox.
build-pkgs: ./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH) \
		./var/docker/$(PYTHON_ENV)/log/build-devel.log build-docker-volumes-$(PYTHON_ENV)
# Defined as a .PHONY recipe so that multiple targets can depend on this as a
# pre-requisite and it will only be run once per invocation.
	rm -vf ./dist/*
# Build Python packages/distributions from the development Docker container for
# consistency/reproducibility.
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) python-project-structure-devel \
	    tox run -e "$(PYTHON_ENV)" --pkg-only
# Copy the wheel to a location accessible to all containers:
	cp -lfv "$$(
	    ls -t ./var/docker/$(PYTHON_ENV)/.tox/.pkg/dist/*.whl | head -n 1
	)" "./dist/"
# Also build the source distribution:
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) python-project-structure-devel \
	    tox run -e "$(PYTHON_ENV)" --override "testenv.package=sdist" --pkg-only
	cp -lfv "$$(
	    ls -t ./var/docker/$(PYTHON_ENV)/.tox/.pkg/dist/*.tar.gz | head -n 1
	)" "./dist/"

.PHONY: $(PYTHON_ENVS:%=build-requirements-%)
### Compile fixed/pinned dependency versions if necessary.
$(PYTHON_ENVS:%=build-requirements-%):
# Avoid parallel tox recreations stomping on each other
	$(MAKE) -e "$(@:build-requirements-%=./var/log/tox/%/build.log)"
	targets="./requirements/$(@:build-requirements-%=%)/user.txt \
	    ./requirements/$(@:build-requirements-%=%)/devel.txt \
	    ./requirements/$(@:build-requirements-%=%)/build.txt \
	    ./build-host/requirements-$(@:build-requirements-%=%).txt"
# Workaround race conditions in pip's HTTP file cache:
# https://github.com/pypa/pip/issues/6970#issuecomment-527678672
	$(MAKE) -e -j $${targets} ||
	    $(MAKE) -e -j $${targets} ||
	    $(MAKE) -e -j $${targets}

## Docker Build Targets:
#
# Strive for as much consistency as possible in development tasks between the local host
# and inside containers.  To that end, most of the `*-docker` container target recipes
# should run the corresponding `*-local` local host target recipes inside the
# development container.  Top level targets, like `test`, should run as much as possible
# inside the development container.

.PHONY: build-docker
### Set up for development in Docker containers.
build-docker: build-pkgs ./var/log/tox/build/build.log
	$(MAKE) -e -j PYTHON_WHEEL="$(call current_pkg,.whl)" \
	    DOCKER_BUILD_ARGS="--progress plain" \
	    $(PYTHON_MINORS:%=build-docker-%)

.PHONY: $(PYTHON_MINORS:%=build-docker-%)
### Set up for development in a Docker container for one Python version.
$(PYTHON_MINORS:%=build-docker-%):
	$(MAKE) -e \
	    PYTHON_MINORS="$(@:build-docker-%=%)" \
	    PYTHON_MINOR="$(@:build-docker-%=%)" \
	    PYTHON_ENV="py$(subst .,,$(@:build-docker-%=%))" \
	    "./var/docker/py$(subst .,,$(@:build-docker-%=%))/log/build-user.log"

.PHONY: build-docker-tags
### Print the list of image tags for the current registry and variant.
build-docker-tags:
	$(MAKE) -e $(DOCKER_REGISTRIES:%=build-docker-tags-%)

.PHONY: $(DOCKER_REGISTRIES:%=build-docker-tags-%)
### Print the list of image tags for the current registry and variant.
$(DOCKER_REGISTRIES:%=build-docker-tags-%): \
		./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH) \
		./var/log/tox/build/build.log
	docker_image=$(DOCKER_IMAGE_$(@:build-docker-tags-%=%))
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)-$(DOCKER_BRANCH_TAG)
ifeq ($(VCS_BRANCH),main)
# Only update tags end users may depend on to be stable from the `main` branch
	VERSION=$$(./.tox/build/bin/cz version --project)
	major_version=$$(echo $${VERSION} | sed -nE 's|([0-9]+).*|\1|p')
	minor_version=$$(
	    echo $${VERSION} | sed -nE 's|([0-9]+\.[0-9]+).*|\1|p'
	)
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)-$${minor_version}
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)-$${major_version}
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)
endif
# This variant is the default used for tags such as `latest`
ifeq ($(PYTHON_MINOR),$(PYTHON_HOST_MINOR))
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(DOCKER_BRANCH_TAG)
ifeq ($(VCS_BRANCH),main)
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$${minor_version}
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$${major_version}
ifeq ($(DOCKER_VARIANT),)
	echo $${docker_image}:latest
else
	echo $${docker_image}:$(DOCKER_VARIANT)
endif
endif
endif

.PHONY: build-docker-build
### Run the actual commands used to build the Docker container image.
build-docker-build: $(HOME)/.local/var/log/docker-multi-platform-host-install.log \
		./var/log/tox/build/build.log \
		./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH) \
		./var/log/docker-login-DOCKER.log
# Workaround broken interactive session detection:
	docker pull "python:$(PYTHON_MINOR)"
	docker_build_caches=""
ifeq ($(GITLAB_CI),true)
# Don't cache when building final releases on `main`
	$(MAKE) -e "./var/log/docker-login-GITLAB.log" || true
ifneq ($(VCS_BRANCH),main)
	if $(MAKE) -e pull-docker
	then
	    docker_build_caches+=" --cache-from $(DOCKER_IMAGE_GITLAB):\
	$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)-$(DOCKER_BRANCH_TAG)"
	fi
endif
endif
ifeq ($(GITHUB_ACTIONS),true)
	$(MAKE) -e "./var/log/docker-login-GITHUB.log" || true
ifneq ($(VCS_BRANCH),main)
	if $(MAKE) -e pull-docker
	then
	    docker_build_caches+=" --cache-from $(DOCKER_IMAGE_GITHUB):\
	$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)-$(DOCKER_BRANCH_TAG)"
	fi
endif
endif
	docker_image_tags=""
	for image_tag in $$(
	    $(MAKE) -e --no-print-directory build-docker-tags
	)
	do
	    docker_image_tags+="--tag $${image_tag} "
	done
# https://github.com/moby/moby/issues/39003#issuecomment-879441675
	docker buildx build $(DOCKER_BUILD_ARGS) \
	    --build-arg BUILDKIT_INLINE_CACHE="1" \
	    --build-arg PYTHON_MINOR="$(PYTHON_MINOR)" \
	    --build-arg PYTHON_ENV="$(PYTHON_ENV)" \
	    --build-arg VERSION="$$(./.tox/build/bin/cz version --project)" \
	    $${docker_image_tags} $${docker_build_caches} --file "$(DOCKER_FILE)" "./"
# Ensure any subsequent builds have optimal caches
ifeq ($(GITLAB_CI),true)
	docker push "$(DOCKER_IMAGE_GITLAB):\
	$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)-$(DOCKER_BRANCH_TAG)"
endif
ifeq ($(GITHUB_ACTIONS),true)
ifneq ($(CI_IS_FORK),true)
	docker push "$(DOCKER_IMAGE_GITHUB):\
	$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)-$(DOCKER_BRANCH_TAG)"
endif
endif

.PHONY: $(PYTHON_MINORS:%=build-docker-requirements-%)
### Pull container images and compile fixed/pinned dependency versions if necessary.
$(PYTHON_MINORS:%=build-docker-requirements-%): ./.env
	export PYTHON_MINOR="$(@:build-docker-requirements-%=%)"
	export PYTHON_ENV="py$(subst .,,$(@:build-docker-requirements-%=%))"
	$(MAKE) -e build-docker-volumes-$${PYTHON_ENV} \
	    "./var/docker/$${PYTHON_ENV}/log/build-devel.log"
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) python-project-structure-devel \
	    make -e PYTHON_MINORS="$(@:build-docker-requirements-%=%)" \
	    PIP_COMPILE_ARGS="$(PIP_COMPILE_ARGS)" \
	    build-requirements-py$(subst .,,$(@:build-docker-requirements-%=%))

.PHONY: $(PYTHON_ENVS:%=build-docker-volumes-%)
### Ensure access permissions to build artifacts in Python version container volumes.
# If created by `# dockerd`, they end up owned by `root`.
$(PYTHON_ENVS:%=build-docker-volumes-%): \
		./src/python_project_structure.egg-info/ ./.tox/
	$(MAKE) -e \
	    $(@:build-docker-volumes-%=./var/docker/%/) \
	    $(@:build-docker-volumes-%=./var/docker/%/python_project_structure.egg-info/) \
	    $(@:build-docker-volumes-%=./var/docker/%/.tox/)


## Test Targets:
#
# Recipes that run the test suite.

.PHONY: test
### Format the code and run the full suite of tests, coverage checks, and linters.
test: test-docker-lint test-docker

.PHONY: test-local
### Run the full suite of tests on the local host.
test-local:
	tox $(TOX_RUN_ARGS) -e "$(TOX_ENV_LIST)"

.PHONY: test-debug
### Run tests in the host environment and invoke the debugger on errors/failures.
test-debug: ./var/log/tox/$(PYTHON_ENV)/editable.log
	$(TOX_EXEC_ARGS) pytest --pdb

.PHONY: test-docker
### Run the full suite of tests, coverage checks, and code linters in containers.
test-docker: build-pkgs ./var/log/tox/build/build.log ./var/log/codecov-install.log
	$(MAKE) -e -j PYTHON_WHEEL="$(call current_pkg,.whl)" \
	    DOCKER_BUILD_ARGS="--progress plain" \
	    DOCKER_COMPOSE_RUN_ARGS="$(DOCKER_COMPOSE_RUN_ARGS) -T" \
	    $(PYTHON_MINORS:%=test-docker-%)

.PHONY: $(PYTHON_MINORS:%=test-docker-%)
### Run the full suite of tests inside a docker container for one Python version.
$(PYTHON_MINORS:%=test-docker-%):
	$(MAKE) -e \
	    PYTHON_MINORS="$(@:test-docker-%=%)" \
	    PYTHON_MINOR="$(@:test-docker-%=%)" \
	    PYTHON_ENV="py$(subst .,,$(@:test-docker-%=%))" \
	    test-docker-pyminor

.PHONY: test-docker-pyminor
### Run the full suite of tests inside a docker container for this Python version.
test-docker-pyminor: build-docker-volumes-$(PYTHON_ENV) build-docker-$(PYTHON_MINOR) \
		./var/log/codecov-install.log
	docker_run_args="--rm"
	if [ ! -t 0 ]
	then
# No fancy output when running in parallel
	    docker_run_args+=" -T"
	fi
# Ensure the dist/package has been correctly installed in the image
	docker compose run --no-deps $${docker_run_args} python-project-structure \
	    python -m pythonprojectstructure --help
	docker compose run --no-deps $${docker_run_args} python-project-structure \
	    python-project-structure --help
# Run from the development Docker container for consistency
	docker compose run $${docker_run_args} python-project-structure-devel \
	    make -e PYTHON_MINORS="$(PYTHON_MINORS)" PYTHON_WHEEL="$(PYTHON_WHEEL)" \
	        test-local
# Upload any build or test artifacts to CI/CD providers
ifeq ($(GITLAB_CI),true)
ifeq ($(PYTHON_MINOR),$(PYTHON_HOST_MINOR))
ifneq ($(CODECOV_TOKEN),)
	codecov --nonZero -t "$(CODECOV_TOKEN)" \
	    --file "./build/$(PYTHON_ENV)/coverage.xml"
else ifneq ($(CI_IS_FORK),true)
	set +x
	echo "ERROR: CODECOV_TOKEN missing from ./.env or CI secrets"
	false
endif
endif
endif

.PHONY: test-docker-lint
### Check the style and content of the `./Dockerfile*` files.
test-docker-lint: ./.env build-docker-volumes-$(PYTHON_ENV) \
		./var/log/docker-login-DOCKER.log
	docker compose pull hadolint
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) hadolint
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) hadolint \
	    hadolint "./Dockerfile.devel"
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) hadolint \
	    hadolint "./build-host/Dockerfile"

.PHONY: test-push
### Perform any checks that should only be run before pushing.
test-push: $(VCS_FETCH_TARGETS) \
		$(HOME)/.local/var/log/python-project-structure-host-install.log \
		./var/docker/$(PYTHON_ENV)/log/build-devel.log \
		build-docker-volumes-$(PYTHON_ENV) ./.env
ifeq ($(CI),true)
ifneq ($(PYTHON_MINOR),$(PYTHON_HOST_MINOR))
# Don't waste CI time, only check for the canonical version:
	exit
endif
endif
ifeq ($(VCS_COMPARE_BRANCH),main)
# On `main`, compare with the previous commit on `main`
	vcs_compare_rev="$(VCS_COMPARE_REMOTE)/$(VCS_COMPARE_BRANCH)^"
else
	vcs_compare_rev="$(VCS_COMPARE_REMOTE)/$(VCS_COMPARE_BRANCH)"
	if ! git fetch "$(VCS_COMPARE_REMOTE)" "$(VCS_COMPARE_BRANCH)"
	then
# Compare with the pre-release branch if this branch hasn't been pushed yet:
	    vcs_compare_rev="$(VCS_COMPARE_REMOTE)/develop"
	fi
endif
	$(TOX_EXEC_BUILD_ARGS) cz check --rev-range "$${vcs_compare_rev}..HEAD"
	exit_code=0
	$(TOX_EXEC_BUILD_ARGS) python ./bin/cz-check-bump --compare-ref \
	    "$${vcs_compare_rev}" || exit_code=$$?
	if (( $$exit_code == 3 || $$exit_code == 21 ))
	then
	    exit
	elif (( $$exit_code != 0 ))
	then
	    exit $$exit_code
	else
	    docker compose run $(DOCKER_COMPOSE_RUN_ARGS) \
	        python-project-structure-devel $(TOX_EXEC_ARGS) \
	        towncrier check --compare-with "$${vcs_compare_rev}"
	fi

.PHONY: test-clean
### Confirm that the checkout is free of uncommitted VCS changes.
test-clean:
	if [ -n "$$(git status --porcelain)" ]
	then
	    set +x
	    echo "Checkout is not clean"
	    false
	fi


## Release Targets:
#
# Recipes that make an changes needed for releases and publish built artifacts to
# end-users.

.PHONY: release
### Publish installable Python packages and container images as required by commits.
release: release-python release-docker

.PHONY: release-python
### Publish installable Python packages to PyPI.
release-python: ./var/log/tox/build/build.log ./var/log/git-remotes.log \
		./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH) \
		~/.pypirc ./.env build-docker-volumes-$(PYTHON_ENV)
# Only release from the `main` or `develop` branches:
ifeq ($(RELEASE_PUBLISH),true)
# Import the private signing key from CI secrets
	$(MAKE) -e ./var/log/gpg-import.log
# Bump the version and build the final release packages:
	$(MAKE) -e build-pkgs
# https://twine.readthedocs.io/en/latest/#using-twine
	./.tox/build/bin/twine check ./dist/python?project?structure-*
# The VCS remote should reflect the release before the release is published to ensure
# that a published release is never *not* reflected in VCS.  Also ensure the tag is in
# place on any mirrors, using multiple `pushurl` remotes, for those project hosts as
# well:
	$(MAKE) -e test-clean
	./.tox/build/bin/twine upload -s -r "$(PYPI_REPO)" \
	    ./dist/python?project?structure-*
	export VERSION=$$(./.tox/build/bin/cz version --project)
# Create a GitLab release
	./.tox/build/bin/twine upload -s -r "gitlab" \
	    ./dist/python?project?structure-*
	release_cli_args="--description ./NEWS-VERSION.rst"
	release_cli_args+=" --tag-name v$${VERSION}"
	release_cli_args+=" --assets-link {\
	\"name\":\"PyPI\",\
	\"url\":\"https://$(PYPI_HOSTNAME)/project/$(CI_PROJECT_NAME)/$${VERSION}/\",\
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
	docker compose pull gitlab-release-cli
	docker compose run --rm gitlab-release-cli release-cli \
	    --server-url "$(CI_SERVER_URL)" --project-id "$(CI_PROJECT_ID)" \
	    create $${release_cli_args}
# Create a GitHub release
	gh release create "v$${VERSION}" $(GITHUB_RELEASE_ARGS) \
	    --notes-file "./NEWS-VERSION.rst" ./dist/python?project?structure-*
endif

.PHONY: release-docker
### Publish all container images to all container registries.
release-docker: build-docker-volumes-$(PYTHON_ENV) build-docker \
		$(DOCKER_REGISTRIES:%=./var/log/docker-login-%.log)
	$(MAKE) -e -j DOCKER_COMPOSE_RUN_ARGS="$(DOCKER_COMPOSE_RUN_ARGS) -T" \
	    $(PYTHON_MINORS:%=release-docker-%)

.PHONY: $(PYTHON_MINORS:%=release-docker-%)
### Publish the container images for one Python version to all container registries.
$(PYTHON_MINORS:%=release-docker-%): \
		$(DOCKER_REGISTRIES:%=./var/log/docker-login-%.log) \
		$(HOME)/.local/var/log/docker-multi-platform-host-install.log
	export PYTHON_ENV="py$(subst .,,$(@:release-docker-%=%))"
# Build other platforms in emulation and rely on the layer cache for bundling the
# previously built native images into the manifests.
	DOCKER_BUILD_ARGS="--push"
ifneq ($(DOCKER_PLATFORMS),)
	DOCKER_BUILD_ARGS+=" --platform $(subst $(EMPTY) ,$(COMMA),$(DOCKER_PLATFORMS))"
endif
	export DOCKER_BUILD_ARGS
# Push the development manifest and images:
	$(MAKE) -e DOCKER_FILE="./Dockerfile.devel" DOCKER_VARIANT="devel" \
	    build-docker-build
# Push the end-user manifest and images:
	PYTHON_WHEEL="$$(ls -t ./dist/*.whl | head -n 1)"
	$(MAKE) -e DOCKER_BUILD_ARGS="$${DOCKER_BUILD_ARGS}\
	    --build-arg PYTHON_WHEEL=$${PYTHON_WHEEL}" build-docker-build
# Update Docker Hub `README.md` from the official/canonical Python version:
ifeq ($(VCS_BRANCH),main)
	if [ "$${PYTHON_ENV}" == "$(PYTHON_HOST_ENV)" ]
	then
	    $(MAKE) -e "./var/log/docker-login-DOCKER.log"
	    docker compose pull pandoc docker-pushrm
	    docker compose run $(DOCKER_COMPOSE_RUN_ARGS) docker-pushrm
	fi
endif

.PHONY: release-bump
### Bump the package version if on a branch that should trigger a release.
release-bump: ~/.gitconfig $(VCS_RELEASE_FETCH_TARGETS) \
		./var/log/git-remotes.log ./var/log/tox/build/build.log \
		./var/docker/$(PYTHON_ENV)/log/build-devel.log \
		./.env build-docker-volumes-$(PYTHON_ENV)
	if ! git diff --cached --exit-code
	then
	    set +x
	    echo "CRITICAL: Cannot bump version with staged changes"
	    false
	fi
# Ensure the local branch is updated to the forthcoming version bump commit:
	git switch -C "$(VCS_BRANCH)" "$$(git rev-parse HEAD)" --
ifeq ($(VCS_BRANCH),main)
	if ! ./.tox/build/bin/python ./bin/get-base-version $$(
	    ./.tox/build/bin/cz version --project
	)
	then
# There's no pre-release for which to publish a final release:
	    exit
	fi
else
# Only release if required by conventional commits:
	exit_code=0
	./.tox/build/bin/python ./bin/cz-check-bump || exit_code=$$?
	if (( $$exit_code == 3 || $$exit_code == 21 ))
	then
# No commits require a release:
	    exit
	elif (( $$exit_code != 0 ))
	then
	    exit $$exit_code
	fi
endif
# Collect the versions involved in this release according to conventional commits:
	cz_bump_args="--check-consistency --no-verify"
ifneq ($(VCS_BRANCH),main)
	cz_bump_args+=" --prerelease beta"
endif
ifeq ($(RELEASE_PUBLISH),true)
	cz_bump_args+=" --gpg-sign"
# Import the private signing key from CI secrets
	$(MAKE) -e ./var/log/gpg-import.log
endif
# Capture the release notes for *just this* release for creating the GitHub release.
# Have to run before the real `$ towncrier build` run without the `--draft` option
# because after that the `newsfragments` will have been deleted.
	next_version=$$(
	    $(TOX_EXEC_BUILD_ARGS) cz bump $${cz_bump_args} --yes --dry-run |
	    sed -nE 's|.* ([^ ]+) *→ *([^ ]+).*|\2|p;q'
	) || true
# Build and stage the release notes to be commited by `$ cz bump`
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) python-project-structure-devel \
	    tox exec $(TOX_EXEC_OPTS) -e "$(PYTHON_ENV)" -qq -- \
	    towncrier build --version "$${next_version}" --draft --yes \
	    >"./NEWS-VERSION.rst"
	git add -- "./NEWS-VERSION.rst"
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) python-project-structure-devel \
	    $(TOX_EXEC_ARGS) towncrier build --version "$${next_version}" --yes
# Increment the version in VCS
	$(TOX_EXEC_BUILD_ARGS) cz bump $${cz_bump_args}
# Ensure the container image reflects the version bump but we don't need to update the
# requirements again.
	touch \
	    $(PYTHON_ENVS:%=./requirements/%/user.txt) \
	    $(PYTHON_ENVS:%=./requirements/%/devel.txt) \
	    $(PYTHON_ENVS:%=./build-host/requirements-%.txt)
# Ensure the image is up-to-date for subsequent recipes.
	$(MAKE) -e "./var/docker/$(PYTHON_ENV)/log/build-user.log"
ifeq ($(VCS_BRANCH),main)
# Merge the bumped version back into `develop`:
	bump_rev="$$(git rev-parse HEAD)"
	git switch -C "develop" --track "$(VCS_COMPARE_REMOTE)/develop" --
	git merge --ff --gpg-sign \
	    -m "Merge branch 'main' release back into develop" "$${bump_rev}"
ifeq ($(CI),true)
	git push --no-verify --tags "$(VCS_COMPARE_REMOTE)" "HEAD:develop"
endif
	git switch -C "$(VCS_BRANCH)" "$${bump_rev}" --
endif
ifneq ($(GITHUB_ACTIONS),true)
ifneq ($(PROJECT_GITHUB_PAT),)
# Ensure the tag is available for creating the GitHub release below but push *before* to
# GitLab to avoid a race with repository mirrorying:
	git push --no-verify --tags "github" "HEAD:$(VCS_BRANCH)"
endif
endif
ifeq ($(CI),true)
	git push --no-verify --tags "$(VCS_REMOTE)" "HEAD:$(VCS_BRANCH)"
endif


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
devel-upgrade: ./.env build-docker-volumes-$(PYTHON_ENV) \
		./var/docker/$(PYTHON_ENV)/log/build-devel.log \
		./var/log/tox/build/build.log
	touch "./setup.cfg" "./requirements/build.txt.in" \
	    "./build-host/requirements.txt.in"
# Ensure the network is create first to avoid race conditions
	docker compose create python-project-structure-devel
	$(MAKE) -e -j PIP_COMPILE_ARGS="--upgrade" \
	    DOCKER_COMPOSE_RUN_ARGS="$(DOCKER_COMPOSE_RUN_ARGS) -T" \
	    $(PYTHON_MINORS:%=build-docker-requirements-%)
# Update VCS hooks from remotes to the latest tag.
	$(TOX_EXEC_BUILD_ARGS) pre-commit autoupdate

.PHONY: devel-upgrade-branch
### Reset an upgrade branch, commit upgraded dependencies on it, and push for review.
devel-upgrade-branch: ~/.gitconfig ./var/log/gpg-import.log \
		./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH) \
		./var/log/git-remotes.log
	remote_branch_exists=false
	if git fetch "$(VCS_REMOTE)" "$(VCS_BRANCH)-upgrade"
	then
	    remote_branch_exists=true
	fi
	git switch -C "$(VCS_BRANCH)-upgrade" --track "$(VCS_BRANCH)" --
	now=$$(date -u)
	$(MAKE) -e devel-upgrade
	if $(MAKE) -e "test-clean"
	then
# No changes from upgrade, exit successfully but push nothing
	    exit
	fi
# Commit the upgrade changes
	echo "Upgrade all requirements to the latest versions as of $${now}." \
	    >"./src/pythonprojectstructure/newsfragments/\
	+upgrade-requirements.bugfix.rst"
	git add --update './build-host/requirements-*.txt' './requirements/*/*.txt' \
	    "./.pre-commit-config.yaml"
	git add \
	    "./src/pythonprojectstructure/newsfragments/\
	+upgrade-requirements.bugfix.rst"
	git_commit_args="--all --gpg-sign"
ifeq ($(CI),true)
# Don't duplicate the CI run from the push below:
	git_push_args+=" --no-verify"
endif
	git commit $${git_commit_args} -m \
	    "fix(deps): Upgrade requirements latest versions"
# Fail if upgrading left untracked files in VCS
	$(MAKE) -e "test-clean"
ifeq ($(CI),true)
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
endif

.PHONY: devel-merge
### Merge this branch with a suffix back into it's un-suffixed upstream.
devel-merge: ~/.gitconfig ./var/log/git-remotes.log \
		./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_MERGE_BRANCH)
	merge_rev="$$(git rev-parse HEAD)"
	git switch -C "$(VCS_MERGE_BRANCH)" --track "$(VCS_REMOTE)/$(VCS_MERGE_BRANCH)"
	git merge --ff --gpg-sign -m \
	    $$'Merge branch \'$(VCS_BRANCH)\' into $(VCS_MERGE_BRANCH)\n\n[ci merge]' \
	    "$${merge_rev}"
ifeq ($(CI),true)
	git push --no-verify --tags "$(VCS_REMOTE)" "HEAD:$(VCS_MERGE_BRANCH)"
endif


## Clean Targets:
#
# Recipes used to restore the checkout to initial conditions.

.PHONY: clean
### Restore the checkout to a state as close to an initial clone as possible.
clean:
	docker compose down --remove-orphans --rmi "all" -v || true
	$(TOX_EXEC_BUILD_ARGS) pre-commit uninstall \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push" \
	    || true
	$(TOX_EXEC_BUILD_ARGS) pre-commit clean || true
	git clean -dfx -e "var/" -e ".env"
	rm -rfv "./var/log/"
	rm -rf "./var/docker/"


## Real Targets:
#
# Recipes that make actual changes and create and update files for the target.

# Manage fixed/pinned versions in `./requirements/**.txt` files.  Has to be run for each
# python version in the virtual environment for that Python version:
# https://github.com/jazzband/pip-tools#cross-environment-usage-of-requirementsinrequirementstxt-and-pip-compile
$(PYTHON_ENVS:%=./requirements/%/devel.txt): ./pyproject.toml ./setup.cfg ./tox.ini
	true DEBUG Updated prereqs: $(?)
	$(MAKE) -e "$(@:requirements/%/devel.txt=./var/log/tox/%/build.log)"
	./.tox/$(@:requirements/%/devel.txt=%)/bin/pip-compile \
	    --resolver "backtracking" $(PIP_COMPILE_ARGS) --extra "devel" \
	    --output-file "$(@)" "$(<)"
	mkdir -pv "./var/log/"
	touch "./var/log/rebuild.log"
$(PYTHON_ENVS:%=./requirements/%/user.txt): ./pyproject.toml ./setup.cfg ./tox.ini
	true DEBUG Updated prereqs: $(?)
	$(MAKE) -e "$(@:requirements/%/user.txt=./var/log/tox/%/build.log)"
	./.tox/$(@:requirements/%/user.txt=%)/bin/pip-compile \
	    --resolver "backtracking" $(PIP_COMPILE_ARGS) --output-file "$(@)" "$(<)"
	mkdir -pv "./var/log/"
	touch "./var/log/rebuild.log"
$(PYTHON_ENVS:%=./build-host/requirements-%.txt): ./build-host/requirements.txt.in
	true DEBUG Updated prereqs: $(?)
	$(MAKE) -e "$(@:build-host/requirements-%.txt=./var/log/tox/%/build.log)"
	./.tox/$(@:build-host/requirements-%.txt=%)/bin/pip-compile \
	    --resolver "backtracking" $(PIP_COMPILE_ARGS) --output-file "$(@)" "$(<)"
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
	mkdir -pv "./var/log/"
	touch "./var/log/rebuild.log"
$(PYTHON_ENVS:%=./requirements/%/build.txt): ./requirements/build.txt.in
	true DEBUG Updated prereqs: $(?)
	$(MAKE) -e "$(@:requirements/%/build.txt=./var/log/tox/%/build.log)"
	./.tox/$(@:requirements/%/build.txt=%)/bin/pip-compile \
	    --resolver "backtracking" $(PIP_COMPILE_ARGS) --output-file "$(@)" "$(<)"

# Targets used as pre-requisites to ensure virtual environments managed by tox have been
# created and can be used directly to save time on Tox's overhead when we don't need
# Tox's logic about when to update/recreate them, e.g.:
#     $ ./.tox/build/bin/cz --help
# Mostly useful for build/release tools.
$(PYTHON_ALL_ENVS:%=./var/log/tox/%/build.log):
	$(MAKE) -e "$(HOME)/.local/var/log/python-project-structure-host-install.log"
	mkdir -pv "$(dir $(@))"
	tox run $(TOX_EXEC_OPTS) -e "$(@:var/log/tox/%/build.log=%)" --notest |&
	    tee -a "$(@)"
# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`.  Use as a
# prerequisite when using Tox-managed virtual environments directly and changes to code
# need to take effect immediately.
$(PYTHON_ENVS:%=./var/log/tox/%/editable.log):
	$(MAKE) -e "$(HOME)/.local/var/log/python-project-structure-host-install.log"
	mkdir -pv "$(dir $(@))"
	tox exec $(TOX_EXEC_OPTS) -e "$(@:var/log/tox/%/editable.log=%)" -- \
	    pip install -e "./" |& tee -a "$(@)"

## Docker real targets:

# Build the development image:
./var/docker/$(PYTHON_ENV)/log/build-devel.log: \
		./Dockerfile.devel ./.dockerignore ./bin/entrypoint \
		./pyproject.toml ./setup.cfg ./tox.ini \
		./build-host/requirements.txt.in ./docker-compose.yml \
		./docker-compose.override.yml ./.env \
		./var/docker/$(PYTHON_ENV)/log/rebuild.log
	true DEBUG Updated prereqs: $(?)
	$(MAKE) -e build-docker-volumes-$(PYTHON_ENV)
	mkdir -pv "$(dir $(@))"
ifeq ($(DOCKER_BUILD_PULL),true)
# Pull the development image and simulate as if it had been built here.
	if $(MAKE) -e DOCKER_VARIANT="devel" pull-docker
	then
	    touch "$(@)" "./var/docker/$(PYTHON_ENV)/log/rebuild.log"
# Ensure the virtualenv in the volume is also current:
	    docker compose run $(DOCKER_COMPOSE_RUN_ARGS) \
	        python-project-structure-devel make -e PYTHON_MINORS="$(PYTHON_MINOR)" \
	        "./var/log/tox/$(PYTHON_ENV)/build.log"
	    exit
	fi
endif
	$(MAKE) -e DOCKER_FILE="./Dockerfile.devel" DOCKER_VARIANT="devel" \
	    build-docker-build >>"$(@)"
# Update the pinned/frozen versions, if needed, using the container.  If changed, then
# we may need to re-build the container image again to ensure it's current and correct.
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) python-project-structure-devel \
	    make -e PYTHON_MINORS="$(PYTHON_MINOR)" build-requirements-$(PYTHON_ENV)
ifeq ($(CI),true)
# On CI, any changes from compiling requirements is a failure so no need to waste time
# rebuilding images:
	touch "$(@)"
else
	$(MAKE) -e "$(@)"
endif

# Build the end-user image:
./var/docker/$(PYTHON_ENV)/log/build-user.log: \
		./var/docker/$(PYTHON_ENV)/log/build-devel.log ./Dockerfile \
		./var/docker/$(PYTHON_ENV)/log/rebuild.log
	true DEBUG Updated prereqs: $(?)
ifeq ($(PYTHON_WHEEL),)
	$(MAKE) -e "build-pkgs"
	PYTHON_WHEEL="$$(ls -t ./dist/*.whl | head -n 1)"
endif
# Build the end-user image now that all required artifacts are built"
	mkdir -pv "$(dir $(@))"
	$(MAKE) -e DOCKER_BUILD_ARGS="$(DOCKER_BUILD_ARGS)\
	    --build-arg PYTHON_WHEEL=$${PYTHON_WHEEL}" build-docker-build >>"$(@)"
# The image installs the host requirements, reflect that in the bind mount volumes
	date >>"$(@:%/build-user.log=%/host-install.log)"

./var/ $(PYTHON_ENVS:%=./var/docker/%/) \
./src/python_project_structure.egg-info/ \
$(PYTHON_ENVS:%=./var/docker/%/python_project_structure.egg-info/) \
./.tox/ $(PYTHON_ENVS:%=./var/docker/%/.tox/):
	mkdir -pv "$(@)"

# Marker file used to trigger the rebuild of the image for just one Python version.
# Useful to workaround async timestamp issues when running jobs in parallel:
./var/docker/$(PYTHON_ENV)/log/rebuild.log:
	mkdir -pv "$(dir $(@))"
	date >>"$(@)"

# Local environment variables from a template:
./.env: ./.env.in
	$(MAKE) -e "template=$(<)" "target=$(@)" expand-template

# Install all tools required by recipes that have to be installed externally on the
# host.  Use a target file outside this checkout to support multiple checkouts.  Use a
# target specific to this project so that other projects can use the same approach but
# with different requirements.
$(HOME)/.local/var/log/python-project-structure-host-install.log:
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
	    if [ -e ./build-host/requirements-$(PYTHON_HOST_ENV).txt ]
	    then
	        pip install -r "./build-host/requirements-$(PYTHON_HOST_ENV).txt"
	    else
	        pip install -r "./build-host/requirements.txt.in"
	    fi
	) |& tee -a "$(@)"

# https://docs.docker.com/build/building/multi-platform/#building-multi-platform-images
$(HOME)/.local/var/log/docker-multi-platform-host-install.log:
	mkdir -pv "$(dir $(@))"
	if ! docker context inspect "multi-platform" |& tee -a "$(@)"
	then
	    docker context create "multi-platform" |& tee -a "$(@)"
	fi
	if ! docker buildx inspect |& tee -a "$(@)" |
	    grep -q '^ *Endpoint: *multi-platform *'
	then
	    docker buildx create --use "multi-platform" |& tee -a "$(@)"
	fi

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

# Retrieve VCS data needed for versioning (tags) and release (release notes).
$(VCS_FETCH_TARGETS): ./.git/logs/HEAD
	git_fetch_args=--tags
	if [ "$$(git rev-parse --is-shallow-repository)" == "true" ]
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

./.git/hooks/pre-commit:
	$(MAKE) -e "$(HOME)/.local/var/log/python-project-structure-host-install.log"
	$(TOX_EXEC_BUILD_ARGS) pre-commit install \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push"

# Capture any project initialization tasks for reference.  Not actually usable.
./pyproject.toml:
	$(MAKE) -e "$(HOME)/.local/var/log/python-project-structure-host-install.log"
	$(TOX_EXEC_BUILD_ARGS) cz init

# Tell Emacs where to find checkout-local tools needed to check the code.
./.dir-locals.el: ./.dir-locals.el.in
	$(MAKE) -e "template=$(<)" "target=$(@)" expand-template

# Ensure minimal VCS configuration, mostly useful in automation such as CI.
~/.gitconfig:
	git config --global user.name "$(USER_FULL_NAME)"
	git config --global user.email "$(USER_EMAIL)"

./var/log/git-remotes.log:
	mkdir -pv "$(dir $(@))"
	set +x
ifneq ($(VCS_REMOTE_PUSH_URL),)
	if ! git remote get-url --push --all "origin" |
	    grep -q -F "$(VCS_REMOTE_PUSH_URL)"
	then
	    echo "INFO:Adding push url for remote 'origin'"
	    git remote set-url --push --add "origin" "$(VCS_REMOTE_PUSH_URL)" |
	        tee -a "$(@)"
	fi
endif
ifneq ($(GITHUB_ACTIONS),true)
ifneq ($(PROJECT_GITHUB_PAT),)
# Also add a fetch remote for the `$ gh ...` CLI tool to detect:
	if ! git remote get-url "github" >"/dev/null"
	then
	    echo "INFO:Adding remote 'github'"
	    git remote add "github" \
	        "https://$(PROJECT_GITHUB_PAT)@github.com/$(CI_PROJECT_PATH).git" |
	        tee -a "$(@)"
	fi
else ifneq ($(CI_IS_FORK),true)
	set +x
	echo "ERROR: PROJECT_GITHUB_PAT missing from ./.env or CI secrets"
	false
endif
endif
	set -x
# Fail fast if there's still no push access
	git push --no-verify --tags "origin" | tee -a "$(@)"

# Ensure release publishing authentication, mostly useful in automation such as CI.
~/.pypirc: ./home/.pypirc.in
	$(MAKE) -e "template=$(<)" "target=$(@)" expand-template

./var/log/docker-login-DOCKER.log: ./.env
	mkdir -pv "$(dir $(@))"
	set +x
	source "./.env"
	export DOCKER_PASS
	if [ -n "$${DOCKER_PASS}" ]
	then
	    set -x
	    printenv "DOCKER_PASS" | docker login -u "merpatterson" --password-stdin
	elif [ "$(CI_IS_FORK)" != "true" ]
	then
	    echo "ERROR: DOCKER_PASS missing from ./.env or CI secrets"
	    false
	fi
	date | tee -a "$(@)"
# TEMPLATE: Add a cleanup rule for the GitLab container registry under the project
# settings.
./var/log/docker-login-GITLAB.log: ./.env
	mkdir -pv "$(dir $(@))"
	set +x
	source "./.env"
	export CI_REGISTRY_PASSWORD
	if [ -n "$${CI_REGISTRY_PASSWORD}" ]
	then
	    set -x
	    printenv "CI_REGISTRY_PASSWORD" |
	        docker login -u "$(CI_REGISTRY_USER)" --password-stdin "$(CI_REGISTRY)"
	elif [ "$(CI_IS_FORK)" != "true" ]
	then
	    echo "ERROR: CI_REGISTRY_PASSWORD missing from ./.env or CI secrets"
	    false
	fi
	date | tee -a "$(@)"
# TEMPLATE: Connect the GitHub container registry to the repository using the `Connect`
# button at the bottom of the container registry's web UI.
./var/log/docker-login-GITHUB.log: ./.env
	mkdir -pv "$(dir $(@))"
	set +x
	source "./.env"
	export PROJECT_GITHUB_PAT
	if [ -n "$${PROJECT_GITHUB_PAT}" ]
	then
	    set -x
	    printenv "PROJECT_GITHUB_PAT" |
	        docker login -u "$(GITHUB_REPOSITORY_OWNER)" --password-stdin "ghcr.io"
	elif [ "$(CI_IS_FORK)" != "true" ]
	then
	    echo "ERROR: PROJECT_GITHUB_PAT missing from ./.env or CI secrets"
	    false
	fi
	date | tee -a "$(@)"

# GPG signing key creation and management in CI
export GPG_PASSPHRASE=
GPG_SIGNING_PRIVATE_KEY=
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
./var/log/gpg-import.log: ~/.gitconfig
# In each CI run, import the private signing key from the CI secrets
	mkdir -pv "$(dir $(@))"
ifneq ($(and $(GPG_SIGNING_PRIVATE_KEY),$(GPG_PASSPHRASE)),)
	printenv "GPG_SIGNING_PRIVATE_KEY" | gpg --batch --import | tee -a "$(@)"
	echo 'default-key:0:"$(GPG_SIGNING_KEYID)' | gpgconf —change-options gpg
	git config --global user.signingkey "$(GPG_SIGNING_KEYID)"
# "Unlock" the signing key for the remainder of this CI run:
	printenv 'GPG_PASSPHRASE' >"./var/ci-cd-signing-subkey.passphrase"
	true | gpg --batch --pinentry-mode "loopback" \
	    --passphrase-file "./var/ci-cd-signing-subkey.passphrase" \
	    --sign | gpg --list-packets
else
ifneq ($(CI_IS_FORK),true)
	set +x
	echo "ERROR: GPG_SIGNING_PRIVATE_KEY or GPG_PASSPHRASE " \
	    "missing from ./.env or CI secrets"
	false
endif
	date | tee -a "$(@)"
endif

# TEMPLATE: Optionally, use the following command to generate a GitLab CI/CD runner
# configuration, register it with your project, compare it with the template
# prerequisite, apply the appropriate changes and then  run using `$ docker compose up
# gitlab-runner`.  Particularly useful to conserve shared runner minutes:
./var/gitlab-runner/config/config.toml: ./gitlab-runner/config/config.toml.in
	docker compose run --rm gitlab-runner register \
	    --url "https://gitlab.com/" --docker-image "docker" --executor "docker"


## Utility Targets:
#
# Recipes used to make similar changes across targets where using Make's basic syntax
# can't be used.

.PHONY: expand-template
## Create a file from a template replacing environment variables
expand-template:
	$(MAKE) -e "$(HOME)/.local/var/log/python-project-structure-host-install.log"
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

.PHONY: pull-docker
### Pull an existing image best to use as a cache for building new images
pull-docker: ./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH) \
		./var/log/tox/build/build.log
	export VERSION=$$(./.tox/build/bin/cz version --project)
	for vcs_branch in $(VCS_BRANCHES)
	do
	    docker_tag="$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)-$${vcs_branch}"
	    for docker_image in $(DOCKER_IMAGES)
	    do
	        if docker pull "$${docker_image}:$${docker_tag}"
	        then
	            docker tag "$${docker_image}:$${docker_tag}" \
	                "$(DOCKER_IMAGE_DOCKER):$${docker_tag}"
	            exit
	        fi
	    done
	done
	set +x
	echo "ERROR: Could not pull any existing docker image"
	false

# TEMPLATE: Run this once for your project.  See the `./var/log/docker-login*.log`
# targets for the authentication environment variables that need to be set or just login
# to those container registries manually and touch these targets.
.PHONY: bootstrap-project
### Run any tasks needed to be run once for a given project by a maintainer
bootstrap-project: \
		./var/log/docker-login-GITLAB.log \
		./var/log/docker-login-GITHUB.log
# Initially seed the build host Docker image to bootstrap CI/CD environments
# GitLab CI/CD:
	$(MAKE) -e -C "./build-host/" DOCKER_IMAGE="$(DOCKER_IMAGE_GITLAB)" release
# GitHub Actions:
	$(MAKE) -e -C "./build-host/" DOCKER_IMAGE="$(DOCKER_IMAGE_GITHUB)" release


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
# If a target is needed by the recipe of another target but should *not* trigger updates
# when it's newer, such as one-time host install tasks, then use that target in a
# sub-make instead of as a prerequisite:
#
#     ./var/log/foo.log:
#         $(MAKE) "./var/log/bar.log"
#
# We use a few more Make features than these core features and welcome further use of
# such features:
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
