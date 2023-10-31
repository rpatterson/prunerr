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
export PROJECT_NAME=prunerr
NPM_SCOPE=rpattersonnet
export DOCKER_USER=merpatterson
# TEMPLATE: See comments towards the bottom and update.
GPG_SIGNING_KEYID=2EFF7CCE6828E359
export DOWNLOAD_VOLUME=$(CHECKOUT_DIR)/var-docker/media/Library/
PRUNERR_CMD=exec
PRUNERR_ARGS=$(PRUNERR_CMD)

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
HOST_PKG_NAMES_GPG=gnupg
HOST_PKG_NAMES_GHCLI=gh
HOST_PKG_NAMES_CURL=curl
HOST_PKG_NAMES_APG=apg
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
HOST_PKG_NAMES_GHCLI=github-cli
endif
HOST_PKG_CMD=$(HOST_PKG_CMD_PREFIX) $(HOST_PKG_BIN)
# Detect Docker command-line baked into the build-host image:
HOST_TARGET_DOCKER:=$(shell which docker)
ifeq ($(HOST_TARGET_DOCKER),)
HOST_TARGET_DOCKER=$(HOST_PREFIX)/bin/docker
endif
HOST_TARGET_PIP:=$(shell which pip3)
ifeq ($(HOST_TARGET_PIP),)
HOST_TARGET_PIP=$(HOST_PREFIX)/bin/pip3
endif

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
# Managed user-specific directory out of the checkout:
# https://specifications.freedesktop.org/basedir-spec/0.8/ar01s03.html
STATE_DIR=$(HOME)/.local/state/$(PROJECT_NAME)
TZ=Etc/UTC
ifneq ("$(wildcard /usr/share/zoneinfo/)","")
TZ:=$(shell \
  realpath --relative-to=/usr/share/zoneinfo/ \
  $(firstword $(realpath /private/etc/localtime /etc/localtime)) \
)
endif
export TZ
export DOCKER_GID:=$(shell getent group "docker" | cut -d ":" -f 3)

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
export PYTHON_MINOR
export PYTHON_ENV=py$(subst .,,$(PYTHON_MINOR))
PYTHON_SHORT_MINORS=$(subst .,,$(PYTHON_MINORS))
PYTHON_ENVS=$(PYTHON_SHORT_MINORS:%=py%)
PYTHON_ALL_ENVS=$(PYTHON_ENVS) build
PYTHON_EXTRAS=test devel
PYTHON_PROJECT_PACKAGE=$(subst -,,$(PROJECT_NAME))
PYTHON_PROJECT_GLOB=$(subst -,?,$(PROJECT_NAME))
export PYTHON_WHEEL=

# Values derived from Version Control Systems (VCS):
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
export VCS_BRANCH
# Find the remote and branch for conventional commits release data:
VCS_COMPARE_REMOTE=$(VCS_UPSTREAM_REMOTE)
ifeq ($(VCS_COMPARE_REMOTE),)
VCS_COMPARE_REMOTE=$(VCS_PUSH_REMOTE)
endif
VCS_COMPARE_BRANCH=$(VCS_UPSTREAM_BRANCH)
ifeq ($(VCS_COMPARE_BRANCH),)
VCS_COMPARE_BRANCH=$(VCS_BRANCH)
endif
# Under CI, verify commits and release notes by comparing this branch with the branch
# maintainers would merge this branch into:
CI=false
ifeq ($(CI),true)
ifeq ($(VCS_COMPARE_BRANCH),develop)
VCS_COMPARE_BRANCH=main
else ifneq ($(VCS_BRANCH),main)
VCS_COMPARE_BRANCH=develop
endif
# If pushing to upstream release branches, get release data compared to the preceding
# release:
else ifeq ($(VCS_COMPARE_BRANCH),develop)
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
# The sequence of branches from which to find closest existing build artifacts, such as
# container images:
VCS_BRANCHES=$(VCS_BRANCH)
ifneq ($(VCS_BRANCH),main)
ifneq ($(VCS_BRANCH),develop)
VCS_BRANCHES+=develop
endif
VCS_BRANCHES+=main
endif
endif

# Run Python tools in isolated environments managed by Tox:
# Values used to run Tox:
TOX_ENV_LIST=$(subst $(EMPTY) ,$(COMMA),$(PYTHON_ENVS))
TOX_RUN_ARGS=run-parallel --parallel auto --parallel-live
ifeq ($(words $(PYTHON_MINORS)),1)
TOX_RUN_ARGS=run
endif
ifneq ($(PYTHON_WHEEL),)
TOX_RUN_ARGS+= --installpkg "$(PYTHON_WHEEL)"
endif
export TOX_RUN_ARGS
# The options that support running arbitrary commands in the venvs managed by tox
# without Tox's startup time:
TOX_EXEC_OPTS=--no-recreate-pkg --skip-pkg-install
TOX_EXEC_ARGS=tox exec $(TOX_EXEC_OPTS) -e "$(PYTHON_DEFAULT_ENV)"
TOX_EXEC_BUILD_ARGS=tox exec $(TOX_EXEC_OPTS) -e "build"
PIP_COMPILE_EXTRA=

# Values used to build Docker images:
DOCKER_FILE=./Dockerfile
export DOCKER_BUILD_ARGS=
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
DOCKER_COMPOSE_RUN_ARGS=
DOCKER_COMPOSE_RUN_ARGS+= --rm
ifeq ($(shell tty),not a tty)
DOCKER_COMPOSE_RUN_ARGS+= -T
endif
export DOCKER_PASS

# Values derived from or overridden by CI environments:
CI_UPSTREAM_NAMESPACE=$(PROJECT_NAMESPACE)
CI_PROJECT_NAME=$(PROJECT_NAME)
ifeq ($(CI),true)
TEMPLATE_IGNORE_EXISTING=true
endif
GITHUB_REPOSITORY_OWNER=$(CI_UPSTREAM_NAMESPACE)
# Is this checkout a fork of the upstream project?:
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
# Take GitHub auth from the environment under GitHub actions but from secrets on other
# project hosts:
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
# Safe defaults for testing the release process without publishing to the official
# project hosting services, indexes, and registries:
export PIP_COMPILE_ARGS=
RELEASE_PUBLISH=false
PYPI_REPO=testpypi
# Safe defaults for testing the release process without publishing to the final/official
# hosts/indexes/registries:
PYPI_HOSTNAME=test.pypi.org
# Publish releases from the `main` or `develop` branches:
ifeq ($(CI),true)
# Compile requirements on CI/CD as a test to make sure the frozen/pinned versions
# reflect all changes to dependencies, but don't upgrade packages so that external
# changes, such as new PyPI releases, don't turn CI/CD red spuriously and unrelated to
# the contributor's actual changes.
export PIP_COMPILE_ARGS=
endif
GITHUB_RELEASE_ARGS=--prerelease
DOCKER_PLATFORMS=
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
# Only build and publish multi-platform images for the canonical Python version:
ifeq ($(PYTHON_MINOR),$(PYTHON_HOST_MINOR))
DOCKER_PLATFORMS=linux/amd64 linux/arm64 linux/arm/v7
endif
endif
endif
CI_REGISTRY_USER=$(CI_PROJECT_NAMESPACE)
# Avoid undefined variables warnings when running under local development:
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

.PHONY: start
## Run the local development end-to-end stack services in the background as daemons.
start: build-docker-$(PYTHON_MINOR) ./.env.~out~
	docker compose down
	docker compose up -d

.PHONY: run
## Run the local development end-to-end stack services in the foreground for debugging.
run: build-docker-$(PYTHON_MINOR) ./.env.~out~
	docker compose down
	docker compose up


### Build Targets:
#
# Recipes that make artifacts needed for by end-users, development tasks, other recipes.

.PHONY: build
## Set up everything for development from a checkout, local and in containers.
build: ./.git/hooks/pre-commit ./.env.~out~ $(HOST_TARGET_DOCKER) \
		$(HOME)/.local/bin/tox ./var/log/npm-install.log build-docker \
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
build-pkgs: $(HOST_TARGET_DOCKER) \
		./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH) \
		./var-docker/$(PYTHON_ENV)/log/build-devel.log
# Defined as a .PHONY recipe so that more than one target can depend on this as a
# pre-requisite and it runs one time:
	rm -vf ./dist/*
# Build Python packages/distributions from the development Docker container for
# consistency/reproducibility.
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) $(PROJECT_NAME)-devel \
	    tox run -e "$(PYTHON_ENV)" --override "testenv.package=external" --pkg-only
# Copy to a location available in the Docker build context:
	cp -lfv ./var-docker/$(PYTHON_ENV)/.tox/.pkg/tmp/dist/* "./dist/"

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


## Docker Build Targets:
#
# Strive for as much consistency as possible in development tasks between the local host
# and inside containers. To that end, most of the `*-docker` container target recipes
# should run the corresponding `*-local` local host target recipes inside the
# development container. Top level targets, such as `test`, should run as much as
# possible inside the development container.

.PHONY: build-docker
## Set up for development in Docker containers.
build-docker: $(HOME)/.local/bin/tox build-pkgs \
		./var-docker/$(PYTHON_ENV)/log/build-user.log
	tox run $(TOX_EXEC_OPTS) --notest -e "build"
	$(MAKE) -e -j PYTHON_WHEEL="$(call current_pkg,.whl)" \
	    DOCKER_BUILD_ARGS="$(DOCKER_BUILD_ARGS) --progress plain" \
	    $(PYTHON_MINORS:%=build-docker-%)

.PHONY: $(PYTHON_MINORS:%=build-docker-%)
## Set up for development in a Docker container for one Python version.
$(PYTHON_MINORS:%=build-docker-%):
	$(MAKE) -e \
	    PYTHON_MINORS="$(@:build-docker-%=%)" \
	    PYTHON_MINOR="$(@:build-docker-%=%)" \
	    PYTHON_ENV="py$(subst .,,$(@:build-docker-%=%))" \
	    "./var-docker/py$(subst .,,$(@:build-docker-%=%))/log/build-user.log"

.PHONY: build-docker-tags
## Print the list of image tags for the current registry and variant.
build-docker-tags:
	$(MAKE) -e $(DOCKER_REGISTRIES:%=build-docker-tags-%)

.PHONY: $(DOCKER_REGISTRIES:%=build-docker-tags-%)
## Print the list of image tags for the current registry and variant.
$(DOCKER_REGISTRIES:%=build-docker-tags-%): $(HOME)/.local/bin/tox
	test -e "./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH)"
	docker_image=$(DOCKER_IMAGE_$(@:build-docker-tags-%=%))
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)-$(DOCKER_BRANCH_TAG)
ifeq ($(VCS_BRANCH),main)
# Update tags users depend on to be stable from the `main` branch:
	VERSION=$$($(TOX_EXEC_BUILD_ARGS) -qq -- cz version --project)
	major_version=$$(echo $${VERSION} | sed -nE 's|([0-9]+).*|\1|p')
	minor_version=$$(
	    echo $${VERSION} | sed -nE 's|([0-9]+\.[0-9]+).*|\1|p'
	)
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)-v$${minor_version}
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)-v$${major_version}
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)
endif
ifeq ($(PYTHON_MINOR),$(PYTHON_HOST_MINOR))
# Use this variant as the default used for tags such as `latest`
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(DOCKER_BRANCH_TAG)
ifeq ($(VCS_BRANCH),main)
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)v$${minor_version}
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)v$${major_version}
ifeq ($(DOCKER_VARIANT),)
	echo $${docker_image}:latest
else
	echo $${docker_image}:$(DOCKER_VARIANT)
endif
endif
endif

.PHONY: build-docker-build
## Run the actual commands used to build the Docker container image.
build-docker-build: ./Dockerfile $(HOST_TARGET_DOCKER) $(HOME)/.local/bin/tox \
		$(HOME)/.local/state/docker-multi-platform/log/host-install.log \
		./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH) \
		./var/log/docker-login-DOCKER.log
# Workaround broken interactive session detection:
	docker pull "python:$(PYTHON_MINOR)"
# Pull images to use as build caches:
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
# Assemble the tags for all the variant permutations:
	$(MAKE) "./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH)"
	docker_build_args=""
	for image_tag in $$(
	    $(MAKE) -e --no-print-directory build-docker-tags
	)
	do
	    docker_build_args+=" --tag $${image_tag}"
	done
ifeq ($(DOCKER_VARIANT),)
	docker_build_args+=" --target user"
else
	docker_build_args+=" --target $(DOCKER_VARIANT)"
endif
# https://github.com/moby/moby/issues/39003#issuecomment-879441675
	docker buildx build $(DOCKER_BUILD_ARGS) \
	    --build-arg BUILDKIT_INLINE_CACHE="1" \
	    --build-arg PYTHON_MINOR="$(PYTHON_MINOR)" \
	    --build-arg PYTHON_ENV="$(PYTHON_ENV)" \
	    --build-arg VERSION="$$(
	        $(TOX_EXEC_BUILD_ARGS) -qq -- cz version --project
	    )" $${docker_build_args} $${docker_build_caches} --file "$(<)" "./"

.PHONY: $(PYTHON_MINORS:%=build-docker-requirements-%)
## Pull container images and compile fixed/pinned dependency versions if necessary.
$(PYTHON_MINORS:%=build-docker-requirements-%): ./.env.~out~
	export PYTHON_MINOR="$(@:build-docker-requirements-%=%)"
	export PYTHON_ENV="py$(subst .,,$(@:build-docker-requirements-%=%))"
	$(MAKE) -e "./var-docker/$${PYTHON_ENV}/log/build-devel.log"
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) $(PROJECT_NAME)-devel \
	    make -e PYTHON_MINORS="$(@:build-docker-requirements-%=%)" \
	    PIP_COMPILE_ARGS="$(PIP_COMPILE_ARGS)" \
	    build-requirements-py$(subst .,,$(@:build-docker-requirements-%=%))


### Test Targets:
#
# Recipes that run the test suite.

.PHONY: test
## Run the full suite of tests, coverage checks, and linters.
test: test-lint test-docker

.PHONY: test-local
## Run the full suite of tests, coverage checks, and linters on the local host.
test-local: $(HOME)/.local/bin/tox $(PYTHON_ENVS:%=build-requirements-%)
	tox $(TOX_RUN_ARGS) --override "testenv.package=external" -e "$(TOX_ENV_LIST)"

.PHONY: test-lint
## Perform any linter or style checks, including non-code checks.
test-lint: $(HOST_TARGET_DOCKER) test-lint-code test-lint-docker test-lint-docs \
		test-lint-prose
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
test-lint-prose: $(HOST_TARGET_DOCKER) $(HOME)/.local/bin/tox \
		./requirements/$(PYTHON_HOST_ENV)/build.txt ./var/log/npm-install.log
# Lint all markup files tracked in VCS with Vale:
# https://vale.sh/docs/topics/scoping/#formats
	git ls-files -co --exclude-standard -z \
	    ':!NEWS*.rst' ':!LICENSES' ':!styles/Vocab/*.txt' ':!requirements/**' |
	    xargs -r -0 -- docker compose run --rm -T vale || true
# Lint all source code files tracked in VCS with Vale:
	git ls-files -co --exclude-standard -z \
	    ':!styles/*/meta.json' ':!styles/*/*.yml' |
	    xargs -r -0 -- \
	    docker compose run --rm -T vale --config="./styles/code.ini" || true
# Lint source code files tracked in VCS but without extensions with Vale:
	git ls-files -co --exclude-standard -z | grep -Ez '^[^.]+$$' |
	    while read -d $$'\0'
	    do
	        cat "$${REPLY}" |
	            docker compose run --rm -T vale --config="./styles/code.ini" \
	                --ext=".pl"
	    done || true
# Run linters implemented in Python:
	tox -e build -x 'testenv:build.commands=bin/test-lint-prose.sh'
# Run linters implemented in JavaScript:
	~/.nvm/nvm-exec npm run lint:prose

.PHONY: test-debug
## Run tests directly on the system and start the debugger on errors or failures.
test-debug: $(HOME)/.local/bin/tox
	$(TOX_EXEC_ARGS) -- pytest --pdb

.PHONY: test-docker
## Run the full suite of tests, coverage checks, and code linters in containers.
test-docker: $(HOST_TARGET_DOCKER) build-docker $(HOME)/.local/bin/tox build-pkgs
	tox run $(TOX_EXEC_OPTS) --notest -e "build"
# Avoid race condition starting service dependencies:
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) $(PROJECT_NAME)-daemon true
	$(MAKE) -e -j PYTHON_WHEEL="$(call current_pkg,.whl)" \
	    DOCKER_BUILD_ARGS="$(DOCKER_BUILD_ARGS) --progress plain" \
	    DOCKER_COMPOSE_RUN_ARGS="$(DOCKER_COMPOSE_RUN_ARGS) -T" \
	    $(PYTHON_MINORS:%=test-docker-%)

.PHONY: $(PYTHON_MINORS:%=test-docker-%)
## Run the full suite of tests inside a docker container for one Python version.
$(PYTHON_MINORS:%=test-docker-%):
	$(MAKE) -e \
	    PYTHON_MINORS="$(@:test-docker-%=%)" \
	    PYTHON_MINOR="$(@:test-docker-%=%)" \
	    PYTHON_ENV="py$(subst .,,$(@:test-docker-%=%))" \
	    test-docker-pyminor

.PHONY: test-docker-pyminor
## Run the full suite of tests inside a docker container for this Python version.
test-docker-pyminor: $(HOST_TARGET_DOCKER) build-docker-$(PYTHON_MINOR)
	docker_run_args="--rm"
	if test ! -t 0
	then
# No fancy output when running in parallel
	    docker_run_args+=" -T"
	fi
# Ensure the dist/package has been correctly installed in the image
	docker compose run --no-deps $${docker_run_args} $(PROJECT_NAME)-daemon \
	    python -m "$(PYTHON_PROJECT_PACKAGE)" --help
	docker compose run --no-deps $${docker_run_args} $(PROJECT_NAME)-daemon \
	    $(PROJECT_NAME) --help
# Run from the development Docker container for consistency:
	docker compose run $${docker_run_args} $(PROJECT_NAME)-devel \
	    make -e PYTHON_MINORS="$(PYTHON_MINORS)" PYTHON_WHEEL="$(PYTHON_WHEEL)" \
	        test-local
# Upload any build or test artifacts to CI/CD providers
ifeq ($(GITLAB_CI),true)
ifeq ($(PYTHON_MINOR),$(PYTHON_HOST_MINOR))
ifneq ($(CODECOV_TOKEN),)
	$(MAKE) "$(HOME)/.local/bin/codecov"
	codecov --nonZero -t "$(CODECOV_TOKEN)" \
	    --file "./build/reports/$(PYTHON_ENV)/coverage.xml"
else ifneq ($(CI_IS_FORK),true)
	set +x
	echo "ERROR: CODECOV_TOKEN missing from ./.env or CI secrets"
	false
endif
endif
endif

.PHONY: test-lint-docker
## Check the style and content of the `./Dockerfile*` files
test-lint-docker: $(HOST_TARGET_DOCKER) ./.env.~out~ ./var/log/docker-login-DOCKER.log
	docker compose pull --quiet hadolint
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) hadolint
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) hadolint \
	    hadolint "./build-host/Dockerfile"
	$(MAKE) -e -j $(PYTHON_MINORS:%=test-lint-docker-volumes-%)
.PHONY: $(PYTHON_MINORS:%=test-lint-docker-volumes-%)
## Prevent Docker volumes owned by `root` for one Python version.
$(PYTHON_MINORS:%=test-lint-docker-volumes-%):
	$(MAKE) -e \
	    PYTHON_MINORS="$(@:test-lint-docker-volumes-%=%)" \
	    PYTHON_MINOR="$(@:test-lint-docker-volumes-%=%)" \
	    PYTHON_ENV="py$(subst .,,$(@:test-lint-docker-volumes-%=%))" \
	    test-lint-docker-volumes
.PHONY: test-lint-docker-volumes
## Prevent Docker volumes owned by `root`.
test-lint-docker-volumes: $(HOST_TARGET_DOCKER) ./.env.~out~
# Ensure that any bind mount volume paths exist in VCS so that `# dockerd` doesn't
# create them as `root`:
	if test -n "$$(
	    ./bin/docker-add-volume-paths.sh "$(CHECKOUT_DIR)" \
	        "/usr/local/src/$(PROJECT_NAME)"
	)"
	then
	    set +x
	    echo "\
	ERROR: Docker bind mount paths didn't exist, force added ignore files.
	       Review ignores above in case they need changes or followup."
	    false
	fi

.PHONY: test-push
## Verify commits before pushing to the remote.
test-push: $(VCS_FETCH_TARGETS) $(HOME)/.local/bin/tox
	vcs_compare_rev="$(VCS_COMPARE_REMOTE)/$(VCS_COMPARE_BRANCH)"
ifeq ($(CI),true)
ifneq ($(PYTHON_MINOR),$(PYTHON_HOST_MINOR))
# Don't waste CI time, only continue for the canonical version:
	exit
endif
ifeq ($(VCS_COMPARE_BRANCH),main)
# On `main`, compare with the preceding commit on `main`:
	vcs_compare_rev="$(VCS_COMPARE_REMOTE)/$(VCS_COMPARE_BRANCH)^"
endif
endif
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
## Publish PyPI packages and Docker images if conventional commits require a release.
release: release-pkgs release-docker

.PHONY: release-pkgs
## Publish installable Python packages to PyPI if conventional commits require.
release-pkgs: $(HOME)/.local/bin/tox ~/.pypirc.~out~ $(HOST_TARGET_DOCKER) \
		./var/log/git-remotes.log \
		./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH) ./.env.~out~ \
		$(HOST_PREFIX)/bin/gh
# Don't release unless from the `main` or `develop` branches:
ifeq ($(RELEASE_PUBLISH),true)
# Import the private signing key from CI secrets
	$(MAKE) -e "./var/log/gpg-import.log"
# Bump the version and build the final release packages:
	$(MAKE) -e build-pkgs
# https://twine.readthedocs.io/en/latest/#using-twine
	$(TOX_EXEC_BUILD_ARGS) -- twine check \
	    ./var-docker/$(PYTHON_ENV)/.tox/.pkg/tmp/dist/*
# Ensure VCS has captured all the effects of building the release:
	$(MAKE) -e test-clean
	$(TOX_EXEC_BUILD_ARGS) -- twine upload -s -r "$(PYPI_REPO)" \
	    ./var-docker/$(PYTHON_ENV)/.tox/.pkg/tmp/dist/*
	export VERSION=$$($(TOX_EXEC_BUILD_ARGS) -qq -- cz version --project)
# Create a GitLab release:
	./.tox/build/bin/twine upload -s -r "gitlab" \
	    ./var-docker/$(PYTHON_ENV)/.tox/.pkg/tmp/dist/*
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
	\"url\":\"https://hub.docker.com/r/$(DOCKER_USER)/$(CI_PROJECT_NAME)/tags\",\
	\"link_type\":\"image\"\
	}"
	docker compose pull gitlab-release-cli
	docker compose run --rm gitlab-release-cli release-cli \
	    --server-url "$(CI_SERVER_URL)" --project-id "$(CI_PROJECT_ID)" \
	    create $${release_cli_args}
# Create a GitHub release
	gh release create "v$${VERSION}" $(GITHUB_RELEASE_ARGS) \
	    --notes-file "./NEWS-VERSION.rst" \
	    ./var-docker/$(PYTHON_ENV)/.tox/.pkg/tmp/dist/*
endif

.PHONY: release-docker
## Publish all container images to all container registries.
release-docker: $(HOST_TARGET_DOCKER) build-docker \
		$(DOCKER_REGISTRIES:%=./var/log/docker-login-%.log) \
		$(HOME)/.local/state/docker-multi-platform/log/host-install.log
	$(MAKE) -e -j DOCKER_COMPOSE_RUN_ARGS="$(DOCKER_COMPOSE_RUN_ARGS) -T" \
	    $(PYTHON_MINORS:%=release-docker-%)

.PHONY: $(PYTHON_MINORS:%=release-docker-%)
## Publish the container images for one Python version to all container registries.
$(PYTHON_MINORS:%=release-docker-%): \
		$(DOCKER_REGISTRIES:%=./var/log/docker-login-%.log) \
		$(HOME)/.local/state/docker-multi-platform/log/host-install.log
	export PYTHON_ENV="py$(subst .,,$(@:release-docker-%=%))"
# Build other platforms in emulation and rely on the layer cache for bundling the
# native images built before into the manifests:
	DOCKER_BUILD_ARGS="$(DOCKER_BUILD_ARGS) --push"
ifneq ($(DOCKER_PLATFORMS),)
	DOCKER_BUILD_ARGS+=" --platform $(subst $(EMPTY) ,$(COMMA),$(DOCKER_PLATFORMS))"
else
endif
	export DOCKER_BUILD_ARGS
# Push the end-user manifest and images:
	PYTHON_WHEEL="$$(ls -t ./dist/*.whl | head -n 1)"
	$(MAKE) -e DOCKER_BUILD_ARGS="$${DOCKER_BUILD_ARGS}\
	    --build-arg PYTHON_WHEEL=$${PYTHON_WHEEL}" build-docker-build
# Push the development manifest and images:
	$(MAKE) -e DOCKER_VARIANT="devel" build-docker-build
# Update Docker Hub `README.md` by using the `./README.rst` reStructuredText version
# using the official/canonical Python version:
ifeq ($(VCS_BRANCH),main)
	if TEST "$${PYTHON_ENV}" = "$(PYTHON_HOST_ENV)"
	then
	    $(MAKE) -e "./var/log/docker-login-DOCKER.log"
	    docker compose pull --quiet pandoc docker-pushrm
	    docker compose up docker-pushrm
	fi
endif

.PHONY: release-bump
## Bump the package version if conventional commits require a release.
release-bump: $(VCS_RELEASE_FETCH_TARGETS) $(HOME)/.local/bin/tox \
		./var/log/npm-install.log \
		./var-docker/$(PYTHON_ENV)/log/build-devel.log ./.env.~out~
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
ifeq ($(RELEASE_PUBLISH),true)
	cz_bump_args+=" --gpg-sign"
# Import the private signing key from CI secrets
	$(MAKE) -e ./var/log/gpg-import.log
endif
	next_version=$$(
	    $(TOX_EXEC_BUILD_ARGS) -qq -- cz bump $${cz_bump_args} --yes --dry-run |
	    sed -nE 's|.* ([^ ]+) *→ *([^ ]+).*|\2|p;q'
	) || true
# Assemble the release notes for this next version:
	$(TOX_EXEC_BUILD_ARGS) -qq -- \
	    towncrier build --version "$${next_version}" --draft --yes \
	    >"./NEWS-VERSION.rst"
	git add -- "./NEWS-VERSION.rst"
# Build and stage the release notes to commit with `$ cz bump`:
	$(TOX_EXEC_BUILD_ARGS) -- towncrier build --version "$${next_version}" --yes
# Bump the version in the NPM package metadata:
	~/.nvm/nvm-exec npm --no-git-tag-version version "$${next_version}"
	git add -- "./package*.json"
# Increment the version in VCS
	$(TOX_EXEC_BUILD_ARGS) -- cz bump $${cz_bump_args}
# Ensure the container image reflects the version bump without updating the requirements
# again:
	touch \
	    $(PYTHON_ENVS:%=./requirements/%/user.txt) \
	    $(PYTHON_ENVS:%=./requirements/%/devel.txt) \
	    $(PYTHON_ENVS:%=./requirements/%/test.txt)
ifeq ($(VCS_BRANCH),main)
# Merge the bumped version back into `develop`:
	$(MAKE) VCS_BRANCH="main" VCS_MERGE_BRANCH="develop" \
	    VCS_REMOTE="$(VCS_COMPARE_REMOTE)" VCS_MERGE_BRANCH="develop" devel-merge
ifeq ($(CI),true)
	git push --no-verify "$(VCS_COMPARE_REMOTE)" "HEAD:develop"
endif
	git switch -C "$(VCS_BRANCH)" "$$(git rev-parse HEAD)"
endif
ifneq ($(GITHUB_ACTIONS),true)
ifneq ($(PROJECT_GITHUB_PAT),)
# Make the tag available for creating the following GitHub release but push to GitHub
# *before* pushing to GitLab to avoid a race with repository mirroring:
	git push --no-verify "github" tag "v$${next_version}"
endif
endif
ifeq ($(CI),true)
# Push only this tag to avoid clashes with any preceding failed release:
	git push --no-verify "$(VCS_REMOTE)" tag "v$${next_version}"
# Also push the branch:
	git push --no-verify "$(VCS_REMOTE)" "HEAD:$(VCS_BRANCH)"
endif


### Development Targets:
#
# Recipes used by developers to make changes to the code.

.PHONY: devel-format
## Automatically correct code in this checkout according to linters and style checkers.
devel-format: $(HOST_TARGET_DOCKER) ./var/log/npm-install.log $(HOME)/.local/bin/tox
# Add license and copyright header to files missing them:
	git ls-files -co --exclude-standard -z ':!*.license' ':!.reuse' ':!LICENSES' \
	    ':!newsfragments/*' ':!NEWS*.rst' ':!styles/*/meta.json' \
	    ':!styles/*/*.yml' ':!requirements/*/*.txt' \
	    ':!src/prunerr/tests/responses/*' ':!src/prunerr/tests/example-5s.mkv' |
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
	    --remove-unused-variables "./src/$(PYTHON_PROJECT_PACKAGE)/" \
	    "./tests/$(PYTHON_PROJECT_PACKAGE)tests/"
	$(TOX_EXEC_ARGS) -- autopep8 -v -i -r "./src/$(PYTHON_PROJECT_PACKAGE)/" \
	    "./tests/$(PYTHON_PROJECT_PACKAGE)tests/"
	$(TOX_EXEC_ARGS) -- black "./src/$(PYTHON_PROJECT_PACKAGE)/" \
	    "./tests/$(PYTHON_PROJECT_PACKAGE)tests/"

.PHONY: devel-upgrade
## Update all locked or frozen dependencies to their most recent available versions.
devel-upgrade: $(HOME)/.local/bin/tox $(HOST_TARGET_DOCKER) ./.env.~out~ build-docker
	touch "./setup.cfg" "./requirements/build.txt.in"
# Ensure the network is create first to avoid race conditions
	docker compose create $(PROJECT_NAME)-devel
	$(MAKE) -e -j PIP_COMPILE_ARGS="--upgrade" \
	    DOCKER_COMPOSE_RUN_ARGS="$(DOCKER_COMPOSE_RUN_ARGS) -T" \
	    $(PYTHON_MINORS:%=build-docker-requirements-%)
# Update VCS integration from remotes to the most recent tag:
	$(TOX_EXEC_BUILD_ARGS) -- pre-commit autoupdate
# Update the Vale style rule definitions:
	touch "./.vale.ini" "./styles/code.ini"
	$(MAKE) "./var/log/vale-rule-levels.log"

.PHONY: devel-upgrade-branch
## Reset an upgrade branch, commit upgraded dependencies on it, and push for review.
devel-upgrade-branch: ./var/log/gpg-import.log \
		./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH) \
		./var/log/git-remotes.log
	if ! $(MAKE) -e "test-clean"
	then
	    set +x
	    echo "ERROR: Can't upgrade with uncommitted changes."
	    exit 1
	fi
	remote_branch_exists=false
	if git fetch "$(VCS_REMOTE)" "$(VCS_BRANCH)-upgrade"
	then
	    remote_branch_exists=true
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
	git_commit_args="--all --gpg-sign"
ifeq ($(CI),true)
# Don't duplicate the CI run from the following push:
	git_push_args+=" --no-verify"
endif
	git commit $${git_commit_args} -m \
	    "fix(deps): Upgrade to most recent versions"
# Fail if upgrading left un-tracked files in VCS:
	$(MAKE) -e "test-clean"
ifeq ($(CI),true)
# Push any upgrades to the remote for review. Specify both the ref and the expected ref
# for `--force-with-lease=` to support pushing to more than one mirror or remote by
# using more than one `pushUrl`:
	git_push_args="--no-verify"
	if test "$${remote_branch_exists=true}" = "true"
	then
	    git_push_args+=" --force-with-lease=\
	$(VCS_BRANCH)-upgrade:$(VCS_REMOTE)/$(VCS_BRANCH)-upgrade"
	fi
	git push $${git_push_args} "$(VCS_REMOTE)" "HEAD:$(VCS_BRANCH)-upgrade"
endif

.PHONY: devel-merge
## Merge this branch with a suffix back into its un-suffixed upstream.
devel-merge: ./var/log/git-remotes.log \
		./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_MERGE_BRANCH)
	merge_rev="$$(git rev-parse HEAD)"
	git switch -C "$(VCS_MERGE_BRANCH)" --track "$(VCS_REMOTE)/$(VCS_MERGE_BRANCH)"
	git merge --ff --gpg-sign -m \
	    $$'Merge branch \'$(VCS_BRANCH)\' into $(VCS_MERGE_BRANCH)\n\n[ci merge]' \
	    "$${merge_rev}"
ifeq ($(CI),true)
	git push --no-verify "$(VCS_REMOTE)" "HEAD:$(VCS_MERGE_BRANCH)"
endif


### Clean Targets:
#
# Recipes used to restore the checkout to initial conditions.

.PHONY: clean
## Restore the checkout to an initial clone state.
clean:
	docker compose down --remove-orphans --rmi "all" -v || true
	$(TOX_EXEC_BUILD_ARGS) -- pre-commit uninstall \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push" \
	    || true
	$(TOX_EXEC_BUILD_ARGS) -- pre-commit clean || true
	git clean -dfx -e "/var" -e "var-docker/" -e "/.env" -e "*~"
	git clean -dfx "./var-docker/py*/.tox/" \
	    "./var-docker/py*/$(PROJECT_NAME).egg-info/"
	rm -rfv "./var/log/" ./var-docker/py*/log/


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
	mkdir -pv "./var/log/"
	touch "./var/log/rebuild.log"
$(PYTHON_ENVS:%=./requirements/%/user.txt): ./pyproject.toml ./setup.cfg ./tox.ini
	true DEBUG Updated prereqs: $(?)
	$(MAKE) -e PYTHON_ENV="$(@:requirements/%/user.txt=%)" PIP_COMPILE_SRC="$(<)" \
	    PIP_COMPILE_OUT="$(@)" build-requirements-compile
	mkdir -pv "./var/log/"
	touch "./var/log/rebuild.log"
$(PYTHON_ENVS:%=./requirements/%/build.txt): ./requirements/build.txt.in
	true DEBUG Updated prereqs: $(?)
	$(MAKE) -e PYTHON_ENV="$(@:requirements/%/build.txt=%)" PIP_COMPILE_SRC="$(<)" \
	    PIP_COMPILE_OUT="$(@)" build-requirements-compile

# Set up release publishing authentication, useful in automation such as CI:
~/.pypirc.~out~: ./home/.pypirc.in
	$(call expand_template,$(<),$(@))

# Capture any project initialization tasks for reference. Not actually usable.
./pyproject.toml:
	$(MAKE) -e "$(HOME)/.local/bin/tox"
	$(TOX_EXEC_BUILD_ARGS) -- cz init


## Docker real targets:

# Build Docker container images.
# Build the development image:
./var-docker/$(PYTHON_ENV)/log/build-devel.log: ./Dockerfile ./.dockerignore \
		./bin/entrypoint.sh ./docker-compose.yml ./docker-compose.override.yml \
		./.env.~out~ ./var-docker/$(PYTHON_ENV)/log/rebuild.log \
		$(HOST_TARGET_DOCKER) ./pyproject.toml ./setup.cfg
	true DEBUG Updated prereqs: $(?)
	mkdir -pv "$(dir $(@))"
ifeq ($(DOCKER_BUILD_PULL),true)
# Pull the development image and simulate building it here:
	if $(MAKE) -e DOCKER_VARIANT="devel" pull-docker
	then
	    touch "$(@)" "./var-docker/$(PYTHON_ENV)/log/rebuild.log"
# Ensure the virtualenv in the volume is also current:
	    docker compose run $(DOCKER_COMPOSE_RUN_ARGS) $(PROJECT_NAME)-devel \
	        tox run $(TOX_EXEC_OPTS) -e "$(PYTHON_ENV)" --notest
	    exit
	fi
endif
	$(MAKE) -e DOCKER_VARIANT="devel" DOCKER_BUILD_ARGS="--load" \
	    build-docker-build | tee -a "$(@)"
# Update the pinned/frozen versions, if needed, using the container.  If changed, then
# the container image might need re-building to ensure it's current and correct.
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) $(PROJECT_NAME)-devel \
	    make -e PYTHON_MINORS="$(PYTHON_MINOR)" build-requirements-$(PYTHON_ENV)
ifeq ($(CI),true)
# On CI, any changes from compiling requirements is a failure so no need to waste time
# rebuilding images:
	touch "$(@)"
else
	$(MAKE) -e "$(@)"
endif
# Build the end-user image:
./var-docker/$(PYTHON_ENV)/log/build-user.log: \
		./var-docker/$(PYTHON_ENV)/log/build-devel.log ./Dockerfile \
		./.dockerignore ./bin/entrypoint.sh \
		./var-docker/$(PYTHON_ENV)/log/rebuild.log
	true DEBUG Updated prereqs: $(?)
ifeq ($(PYTHON_WHEEL),)
	$(MAKE) -e "build-pkgs"
	PYTHON_WHEEL="$$(ls -t ./dist/*.whl | head -n 1)"
endif
# Build the user image after building all required artifacts:
	mkdir -pv "$(dir $(@))"
	$(MAKE) -e DOCKER_BUILD_ARGS="$(DOCKER_BUILD_ARGS) --load \
	--build-arg PYTHON_WHEEL=$${PYTHON_WHEEL}" build-docker-build >>"$(@)"
# Marker file used to trigger the rebuild of the image.
# Useful to workaround asynchronous timestamp issues when running jobs in parallel:
./var-docker/$(PYTHON_ENV)/log/rebuild.log:
	mkdir -pv "$(dir $(@))"
	date >>"$(@)"
# https://docs.docker.com/build/building/multi-platform/#building-multi-platform-images
$(HOME)/.local/state/docker-multi-platform/log/host-install.log:
	$(MAKE) "$(HOST_TARGET_DOCKER)"
	mkdir -pv "$(dir $(@))"
	if ! docker context inspect "multi-platform" |& tee -a "$(@)"
	then
	    docker context create "multi-platform" |& tee -a "$(@)"
	fi
	if ! docker buildx inspect |& tee -a "$(@)" |
	    grep -q '^ *Endpoint: *multi-platform *'
	then
	    (
	        docker buildx create --use "multi-platform" || true
	    ) |& tee -a "$(@)"
	fi
./var/log/docker-login-DOCKER.log:
	$(MAKE) "$(HOST_TARGET_DOCKER)" "./.env.~out~"
	mkdir -pv "$(dir $(@))"
	if test -n "$${DOCKER_PASS}"
	then
	    printenv "DOCKER_PASS" | docker login -u "$(DOCKER_USER)" --password-stdin
	elif test "$(CI_IS_FORK)" != "true"
	then
	    echo "ERROR: DOCKER_PASS missing from ./.env or CI secrets"
	    false
	fi
	date | tee -a "$(@)"
./var/log/docker-login-GITLAB.log:
	$(MAKE) "./.env.~out~"
	mkdir -pv "$(dir $(@))"
	if test -n "$${CI_REGISTRY_PASSWORD}"
	then
	    printenv "CI_REGISTRY_PASSWORD" |
	        docker login -u "$(CI_REGISTRY_USER)" --password-stdin "$(CI_REGISTRY)"
	elif test "$(CI_IS_FORK)" != "true"
	then
	    echo "ERROR: CI_REGISTRY_PASSWORD missing from ./.env or CI secrets"
	    false
	fi
	date | tee -a "$(@)"
./var/log/docker-login-GITHUB.log:
	$(MAKE) "./.env.~out~"
	mkdir -pv "$(dir $(@))"
	if test -n "$${PROJECT_GITHUB_PAT}"
	then
	    printenv "PROJECT_GITHUB_PAT" |
	        docker login -u "$(GITHUB_REPOSITORY_OWNER)" --password-stdin "ghcr.io"
	elif test "$(CI_IS_FORK)" != "true"
	then
	    echo "ERROR: PROJECT_GITHUB_PAT missing from ./.env or CI secrets"
	    false
	fi
	date | tee -a "$(@)"

# Local environment variables and secrets from a template:
./.env.~out~: ./.env.in
	export TRANSMISSION_PASS="$$(apg -M ncl -n 1)"
	$(call expand_template,$(<),$(@))

./README.md: README.rst
	$(MAKE) "$(HOST_TARGET_DOCKER)"
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
# Initialize minimal VCS configuration, useful in automation such as CI:
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
# Also add a fetch remote for the `$ gh` command-line tool to detect:
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
# Fail fast if there's still no push access:
	git push --no-verify "origin" "HEAD:$(VCS_BRANCH)" | tee -a "$(@)"

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
	$(MAKE) "$(HOST_TARGET_DOCKER)"
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
$(HOME)/.local/bin/tox:
	$(MAKE) "$(HOME)/.local/bin/pipx"
# https://tox.wiki/en/latest/installation.html#via-pipx
	pipx install "tox"
$(HOME)/.local/bin/pipx:
	$(MAKE) "$(HOST_TARGET_PIP)"
# https://pypa.github.io/pipx/installation/#install-pipx
	pip3 install --user "pipx"
	python3 -m pipx ensurepath
$(HOST_TARGET_PIP):
	$(MAKE) "$(STATE_DIR)/log/host-update.log"
	$(HOST_PKG_CMD) $(HOST_PKG_INSTALL_ARGS) "$(HOST_PKG_NAMES_PIP)"

# Manage tools in containers:
$(HOST_TARGET_DOCKER):
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

# Install the code test coverage publishing tool:
$(HOME)/.local/bin/codecov: ./build-host/bin/install-codecov.sh $(HOST_PREFIX)/bin/curl
	"$(<)"
$(HOST_PREFIX)/bin/curl:
	$(MAKE) "$(STATE_DIR)/log/host-update.log"
	$(HOST_PKG_CMD) $(HOST_PKG_INSTALL_ARGS) "$(HOST_PKG_NAMES_CURL)"

# GNU Privacy Guard (GPG) signing key creation and management in CI:
export GPG_PASSPHRASE=
GPG_SIGNING_PRIVATE_KEY=
./var/ci-cd-signing-subkey.asc: $(HOST_PREFIX)/bin/gpg
# Signing release commits and artifacts requires a GPG private key in the CI/CD
# environment. Use a subkey that you can revoke without affecting your main key. This
# recipe captures what I had to do to export a private signing subkey. It's not widely
# tested so you should probably only use this for reference. It worked for me but this
# process risks leaking your main private key so confirm all your assumptions and
# results well.
#
# 1. Create a signing subkey with a *new*, *separate* passphrase:
#    https://wiki.debian.org/Subkeys#How.3F
# 2. Get the long key ID for that private subkey:
#	gpg --list-secret-keys --keyid-format "long"
# 3. Export *only* that private subkey and verify that the main secret key packet is the
#    GPG dummy packet and that the only other private key included is the intended
#    subkey:
#	gpg --armor --export-secret-subkeys "$(GPG_SIGNING_KEYID)!" |
#	    gpg --list-packets
# 4. Export that key as text to a file:
	gpg --armor --export-secret-subkeys "$(GPG_SIGNING_KEYID)!" >"$(@)"
# 5. Confirm that a temporary GNU PG directory can import the exported key and that it
#    can sign files:
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
./var/log/gpg-import.log: $(HOST_PREFIX)/bin/gpg
# In each CI run, import the private signing key from the CI secrets
	mkdir -pv "$(dir $(@))"
ifneq ($(and $(GPG_SIGNING_PRIVATE_KEY),$(GPG_PASSPHRASE)),)
	printenv "GPG_SIGNING_PRIVATE_KEY" | gpg --batch --import | tee -a "$(@)"
	echo 'default-key:0:"$(GPG_SIGNING_KEYID)' | gpgconf —change-options gpg
	git config --global user.signingkey "$(GPG_SIGNING_KEYID)"
# "Unlock" the signing key for the rest of this CI run:
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
$(HOST_PREFIX)/bin/gpg:
	$(MAKE) "$(STATE_DIR)/log/host-update.log"
	$(HOST_PKG_CMD) $(HOST_PKG_INSTALL_ARGS) "$(HOST_PKG_NAMES_GPG)"

$(HOST_PREFIX)/bin/gh:
	$(MAKE) "$(STATE_DIR)/log/host-update.log"
	$(HOST_PKG_CMD) $(HOST_PKG_INSTALL_ARGS) "$(HOST_PKG_NAMES_GHCLI)"

./var/gitlab-runner/config/config.toml: ./gitlab-runner/config/config.toml.in
	docker compose run --rm gitlab-runner register \
	    --url "https://gitlab.com/" --docker-image "docker" --executor "docker"

$(HOST_PREFIX)/bin/apg:
	$(MAKE) "$(STATE_DIR)/log/host-update.log"
	$(HOST_PKG_CMD) $(HOST_PKG_INSTALL_ARGS) "$(HOST_PKG_NAMES_APG)"


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
if test "$(CI)" != "true"
then
    envsubst <"$(1)" | diff -u "$(2:%.~out~=%)" "-" || true
fi
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


### Maintainer targets:
#
# Recipes not used during the usual course of development.

.PHONY: pull-docker
## Pull an existing image best to use as a cache for building new images
pull-docker: ./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH) $(HOST_TARGET_DOCKER)
	export VERSION=$$($(TOX_EXEC_BUILD_ARGS) -qq -- cz version --project)
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

.PHONY: bootstrap-project
bootstrap-project: ./var/log/docker-login-GITLAB.log ./var/log/docker-login-GITHUB.log
# Initially seed the build host Docker image to bootstrap CI/CD environments
# GitLab CI/CD:
	$(MAKE) -e -C "./build-host/" DOCKER_IMAGE="$(DOCKER_IMAGE_GITLAB)" release
# GitHub Actions:
	$(MAKE) -e -C "./build-host/" DOCKER_IMAGE="$(DOCKER_IMAGE_GITHUB)" release
