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
export DOCKER_USER=merpatterson

# Variables used as options to control behavior:
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
# Detect host binaries baked into base images:
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
PYTHON_LATEST_MINOR=$(firstword $(PYTHON_SUPPORTED_MINORS))
PYTHON_LATEST_ENV=py$(subst .,,$(PYTHON_LATEST_MINOR))
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
ifneq ($(PYTHON_WHEEL),)
TOX_RUN_ARGS+= --installpkg "$(PYTHON_WHEEL)"
endif
export TOX_RUN_ARGS
# The options that support running arbitrary commands in the venvs managed by tox with
# the least overhead:
TOX_EXEC_OPTS=--no-recreate-pkg --skip-pkg-install
TOX_EXEC_ARGS=tox exec $(TOX_EXEC_OPTS) -e "$(PYTHON_ENV)"
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
DOCKER_REGISTRIES=DOCKER
export DOCKER_REGISTRY=$(firstword $(DOCKER_REGISTRIES))
DOCKER_IMAGE_DOCKER=$(DOCKER_USER)/$(PROJECT_NAME)
DOCKER_IMAGE=$(DOCKER_IMAGE_$(DOCKER_REGISTRY))
# Values used to run built images in containers:
DOCKER_COMPOSE_RUN_ARGS=
DOCKER_COMPOSE_RUN_ARGS+= --rm
ifeq ($(shell tty),not a tty)
DOCKER_COMPOSE_RUN_ARGS+= -T
endif
export DOCKER_PASS

# Values used for publishing releases:
# Safe defaults for testing the release process without publishing to the official
# project hosting services, indexes, and registries:
RELEASE_PUBLISH=false
PYPI_REPO=testpypi
# Publish releases from the `main` or `develop` branches:
ifeq ($(VCS_BRANCH),main)
RELEASE_PUBLISH=true
else ifeq ($(VCS_BRANCH),develop)
# Publish pre-releases from the `develop` branch:
RELEASE_PUBLISH=true
endif
DOCKER_PLATFORMS=
ifeq ($(RELEASE_PUBLISH),true)
PYPI_REPO=pypi
# Only build and publish multi-platform images for the canonical Python version:
ifeq ($(PYTHON_MINOR),$(PYTHON_HOST_MINOR))
# TEMPLATE: Choose the platforms on which your users run the image. These default
# platforms should cover most common end-user platforms, including modern Apple M1 CPUs,
# Raspberry Pi devices, and AWS Graviton instances:
DOCKER_PLATFORMS=linux/amd64 linux/arm64 linux/arm/v7
endif
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

.PHONY: start
## Run the local development end-to-end stack services in the background as daemons.
start: build-docker-$(PYTHON_MINOR) ./.env.~out~
	docker compose down
	docker compose up -d

.PHONY: run
## Run the local development end-to-end stack services in the foreground for debugging.
run: build-docker ./.env.~out~
	docker compose down
	docker compose up


### Build Targets:
#
# Recipes that make artifacts needed for by end-users, development tasks, other recipes.

.PHONY: build
## Set up everything for development from a checkout, local and in containers.
build: ./.git/hooks/pre-commit ./.env.~out~ $(HOST_TARGET_DOCKER) \
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
	pip_compile_opts="--resolver backtracking --upgrade"
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
	    tox run -e "$(PYTHON_ENV)" --pkg-only
# Copy the wheel to a location available to all containers:
	cp -lfv "$$(
	    ls -t ./var-docker/$(PYTHON_ENV)/.tox/.pkg/dist/*.whl | head -n 1
	)" "./dist/"
# Also build the source distribution:
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) $(PROJECT_NAME)-devel \
	    tox run -e "$(PYTHON_ENV)" --override "testenv.package=sdist" --pkg-only
	cp -lfv "$$(
	    ls -t ./var-docker/$(PYTHON_ENV)/.tox/.pkg/dist/*.tar.gz | head -n 1
	)" "./dist/"

.PHONY: build-docs
## Render the static HTML form of the Sphinx documentation
build-docs: build-docs-html

.PHONY: build-docs-watch
## Serve the Sphinx documentation with live updates
build-docs-watch: $(HOME)/.local/bin/tox
	tox exec -e "build" -- sphinx-watch "./docs/" "./build/docs/html/" "html" --httpd

.PHONY: build-docs-%
build-docs-%: $(HOME)/.local/bin/tox
	tox exec -e "build" -- sphinx-build -M "$(@:build-docs-%=%)" \
	    "./docs/" "./build/docs/"

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
	    )" $${docker_build_args} --file "$(<)" "./"

.PHONY: $(PYTHON_MINORS:%=build-docker-requirements-%)
## Pull container images and compile fixed/pinned dependency versions if necessary.
$(PYTHON_MINORS:%=build-docker-requirements-%): ./.env.~out~
	export PYTHON_MINOR="$(@:build-docker-requirements-%=%)"
	export PYTHON_ENV="py$(subst .,,$(@:build-docker-requirements-%=%))"
	$(MAKE) -e "./var-docker/$${PYTHON_ENV}/log/build-devel.log"
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) $(PROJECT_NAME)-devel \
	    make -e PYTHON_MINORS="$(@:build-docker-requirements-%=%)" \
	    build-requirements-py$(subst .,,$(@:build-docker-requirements-%=%))


### Test Targets:
#
# Recipes that run the test suite.

.PHONY: test
## Run the full suite of tests, coverage checks, and linters.
test: test-lint test-docker

.PHONY: test-local
## Run the full suite of tests, coverage checks, and linters on the local host.
test-local: $(HOME)/.local/bin/tox
	tox $(TOX_RUN_ARGS) -e "$(TOX_ENV_LIST)"

.PHONY: test-lint
## Perform any linter or style checks, including non-code checks.
test-lint: $(HOME)/.local/bin/tox $(HOST_TARGET_DOCKER) ./var/log/npm-install.log \
		build-docs test-lint-docker test-lint-prose
# Run linters implemented in Python:
	tox run -e "build"
# Lint copyright and licensing:
	docker compose run --rm -T "reuse"
# Run linters implemented in JavaScript:
	~/.nvm/nvm-exec npm run lint

.PHONY: test-lint-prose
## Lint prose text for spelling, grammar, and style
test-lint-prose: $(HOST_TARGET_DOCKER) ./var/log/vale-sync.log ./.vale.ini \
		./styles/code.ini
# Lint all markup files tracked in VCS with Vale:
# https://vale.sh/docs/topics/scoping/#formats
	git ls-files -co --exclude-standard -z |
	    xargs -r -0 -t -- docker compose run --rm -T vale
# Lint all source code files tracked in VCS with Vale:
	git ls-files -co --exclude-standard -z |
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

.PHONY: test-debug
## Run tests directly on the system and start the debugger on errors or failures.
test-debug: $(HOME)/.local/bin/tox ./.tox/$(PYTHON_ENV)/log/editable.log
	$(TOX_EXEC_ARGS) -- pytest --pdb

.PHONY: test-docker
## Run the full suite of tests, coverage checks, and code linters in containers.
test-docker: $(HOME)/.local/bin/tox build-pkgs
	tox run $(TOX_EXEC_OPTS) --notest -e "build"
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
	if [ ! -t 0 ]
	then
# No fancy output when running in parallel
	    docker_run_args+=" -T"
	fi
# Ensure the dist/package has been correctly installed in the image
	docker compose run --no-deps $${docker_run_args} $(PROJECT_NAME) python -c \
	    'import $(PYTHON_PROJECT_PACKAGE); print($(PYTHON_PROJECT_PACKAGE))'
# Run from the development Docker container for consistency:
	docker compose run $${docker_run_args} $(PROJECT_NAME)-devel \
	    make -e PYTHON_MINORS="$(PYTHON_MINORS)" PYTHON_WHEEL="$(PYTHON_WHEEL)" \
	        test-local

.PHONY: test-lint-docker
## Check the style and content of the `./Dockerfile*` files
test-lint-docker: $(HOST_TARGET_DOCKER) ./.env.~out~ ./var/log/docker-login-DOCKER.log
	docker compose pull --quiet hadolint
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) hadolint
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) hadolint \
	    hadolint "./build-host/Dockerfile"

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
	if [ -n "$$(git status --porcelain)" ]
	then
	    set +x
	    echo "Checkout is not clean"
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
release-pkgs: $(HOME)/.local/bin/tox ~/.pypirc.~out~
# Don't release unless from the `main` or `develop` branches:
ifeq ($(RELEASE_PUBLISH),true)
	$(MAKE) -e build-pkgs
# https://twine.readthedocs.io/en/latest/#using-twine
	$(TOX_EXEC_BUILD_ARGS) -- twine check ./dist/$(PYTHON_PROJECT_GLOB)-*
# The VCS remote should reflect the release before publishing the release to ensure that
# a published release is never *not* reflected in VCS.
	$(MAKE) -e test-clean
	$(TOX_EXEC_BUILD_ARGS) -- twine upload -s -r "$(PYPI_REPO)" \
	    ./dist/$(PYTHON_PROJECT_GLOB)-*
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
	if [ "$${PYTHON_ENV}" == "$(PYTHON_HOST_ENV)" ]
	then
	    $(MAKE) -e "./var/log/docker-login-DOCKER.log"
	    docker compose pull --quiet pandoc docker-pushrm
	    docker compose up docker-pushrm
	fi
endif

.PHONY: release-bump
## Bump the package version if conventional commits require a release.
release-bump: ~/.gitconfig $(VCS_RELEASE_FETCH_TARGETS) $(HOME)/.local/bin/tox \
		./var/log/npm-install.log ./var/log/git-remotes.log \
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
	if [ "$(VCS_BRANCH)" = "main" ] &&
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
# Ensure the container image reflects the version bump without updating the requirements
# again:
	touch \
	    $(PYTHON_ENVS:%=./requirements/%/user.txt) \
	    $(PYTHON_ENVS:%=./requirements/%/devel.txt) \
	    $(PYTHON_ENVS:%=./build-host/requirements-%.txt)
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
devel-format: $(HOST_TARGET_DOCKER) ./var/log/npm-install.log $(HOME)/.local/bin/tox
# Add license and copyright header to files missing them:
	git ls-files -co --exclude-standard -z |
	grep -Ezv '\.license$$|^(\.reuse|LICENSES)/' |
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
	$(TOX_EXEC_ARGS) -- reuse addheader -r --skip-unrecognised \
	    --copyright "Ross Patterson <me@rpatterson.net>" --license "MIT" "./"

.PHONY: devel-upgrade
## Update all locked or frozen dependencies to their most recent available versions.
devel-upgrade: $(HOME)/.local/bin/tox $(HOST_TARGET_DOCKER) ./.env.~out~ \
		build-docker
	touch "./setup.cfg" "./requirements/build.txt.in"
# Ensure the network is create first to avoid race conditions
	docker compose create $(PROJECT_NAME)-devel
	$(MAKE) -e -j PIP_COMPILE_ARGS="--upgrade" \
	    DOCKER_COMPOSE_RUN_ARGS="$(DOCKER_COMPOSE_RUN_ARGS) -T" \
	    $(PYTHON_MINORS:%=build-docker-requirements-%)
# Update VCS integration from remotes to the most recent tag:
	$(TOX_EXEC_BUILD_ARGS) -- pre-commit autoupdate

.PHONY: devel-upgrade-branch
## Reset an upgrade branch, commit upgraded dependencies on it, and push for review.
devel-upgrade-branch: ~/.gitconfig ./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH)
	git switch -C "$(VCS_BRANCH)-upgrade"
	now=$$(date -u)
	$(MAKE) -e devel-upgrade
	if $(MAKE) -e "test-clean"
	then
# No changes from upgrade, exit signaling success but push nothing:
	    exit
	fi
# Commit the upgrade changes
	echo "Upgrade all requirements to the most recent versions as of $${now}." \
	    >"./newsfragments/+upgrade-requirements.bugfix.rst"
	git add --update './requirements/*/*.txt' "./.pre-commit-config.yaml"
	git add "./newsfragments/+upgrade-requirements.bugfix.rst"
	git commit --all --gpg-sign -m \
	    "fix(deps): Upgrade to most recent versions"
# Fail if upgrading left un-tracked files in VCS:
	$(MAKE) -e "test-clean"

.PHONY: devel-merge
## Merge this branch with a suffix back into its un-suffixed upstream.
devel-merge: ~/.gitconfig ./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_MERGE_BRANCH)
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
	docker compose down --remove-orphans --rmi "all" -v || true
	$(TOX_EXEC_BUILD_ARGS) -- pre-commit uninstall \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push" \
	    || true
	$(TOX_EXEC_BUILD_ARGS) -- pre-commit clean || true
	git clean -dfx -e "/var" -e "var-docker/" -e "/.env" -e "*~"
	git clean -dfx "./var-docker/py*/.tox/" \
	    "./var-docker/py*/project_structure.egg-info/"
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

# Capture any project initialization tasks for reference. Not actually usable.
./pyproject.toml:
	$(MAKE) -e "$(HOME)/.local/bin/tox"
	$(TOX_EXEC_BUILD_ARGS) -- cz init

## Docker real targets:

# Build the development image:
./var-docker/$(PYTHON_ENV)/log/build-devel.log: ./Dockerfile ./.dockerignore \
		./bin/entrypoint ./docker-compose.yml ./docker-compose.override.yml \
		./.env.~out~ ./var-docker/$(PYTHON_ENV)/log/rebuild.log \
		$(HOST_TARGET_DOCKER) ./pyproject.toml ./setup.cfg ./tox.ini
	true DEBUG Updated prereqs: $(?)
	mkdir -pv "$(dir $(@))"
ifeq ($(DOCKER_BUILD_PULL),true)
# Pull the development image and simulate building it here:
	if docker compose pull --quiet $(PROJECT_NAME)-devel
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
	$(MAKE) -e "$(@)"

# Build the end-user image:
./var-docker/$(PYTHON_ENV)/log/build-user.log: \
		./var-docker/$(PYTHON_ENV)/log/build-devel.log ./Dockerfile \
		./.dockerignore ./bin/entrypoint \
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

# Marker file used to trigger the rebuild of the image for only one Python version.
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

# Local environment variables and secrets from a template:
./.env.~out~: ./.env.in
	$(call expand_template,$(<),$(@))

./README.md: README.rst
	$(MAKE) "$(HOST_TARGET_DOCKER)"
	docker compose run --rm "pandoc"


### Development Tools:

# VCS configuration and integration:
# Retrieve VCS data needed for versioning, tags, and releases, release notes:
$(VCS_FETCH_TARGETS): ./.git/logs/HEAD
	git_fetch_args="--tags --prune --prune-tags --force"
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
	$(MAKE) -e "$(HOME)/.local/bin/tox"
	$(TOX_EXEC_BUILD_ARGS) -- pre-commit install \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push"
# Initialize minimal VCS configuration, useful in automation such as CI:
~/.gitconfig:
	git config --global user.name "$(USER_FULL_NAME)"
	git config --global user.email "$(USER_EMAIL)"

# Prose linting:
# Set Vale levels for added style rules:
./.vale.ini ./styles/code.ini:
	$(MAKE)-e "$(HOME)/.local/bin/tox" "./var/log/vale-sync.log"
	$(TOX_EXEC_BUILD_ARGS) -- python ./bin/vale-set-rule-levels.py --input="$(@)"

./var/log/vale-sync.log: ./.env.~out~ ./.vale.ini ./styles/code.ini
	$(MAKE) "$(HOST_TARGET_DOCKER)"
	mkdir -pv "$(dir $(@))"
	docker compose run --rm vale sync | tee -a "$(@)"

# Editor and IDE support and integration:
./.dir-locals.el.~out~: ./.dir-locals.el.in
	$(call expand_template,$(<),$(@))

# Manage JavaScript tools:
./var/log/npm-install.log: ./package.json ./var/log/nvm-install.log
	mkdir -pv "$(dir $(@))"
	~/.nvm/nvm-exec npm install | tee -a "$(@)"
./package.json:
	$(MAKE) "./var/log/nvm-install.log" "$(HOME)/.npmrc"
# https://docs.npmjs.com/creating-a-package-json-file#creating-a-default-packagejson-file
	~/.nvm/nvm-exec npm init --yes --scope="@$(NPM_SCOPE)"
$(HOME)/.npmrc:
	$(MAKE) "./var/log/nvm-install.log"
# https://docs.npmjs.com/creating-a-package-json-file#setting-config-options-for-the-init-command
	~/.nvm/nvm-exec npm set init-author-email "$(USER_EMAIL)"
	~/.nvm/nvm-exec npm set init-author-name "$(USER_FULL_NAME)"
	~/.nvm/nvm-exec npm set init-license "MIT"
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
# created so other targets can use them directly to save time on Tox's overhead when
# they don't need Tox's logic about when to update/recreate them, e.g.:
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

# Set up release publishing authentication, useful in automation such as CI:
~/.pypirc.~out~: ./home/.pypirc.in
	$(call expand_template,$(<),$(@))

./var/log/docker-login-DOCKER.log:
	$(MAKE) "$(HOST_TARGET_DOCKER)" "./.env.~out~"
	mkdir -pv "$(dir $(@))"
	if [ -n "$${DOCKER_PASS}" ]
	then
	    printenv "DOCKER_PASS" | docker login -u "$(DOCKER_USER)" --password-stdin
	elif [ "$(CI_IS_FORK)" != "true" ]
	then
	    echo "ERROR: DOCKER_PASS missing from ./.env"
	    false
	fi
	date | tee -a "$(@)"


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
if [ "$(2:%.~out~=%)" -nt "$(1)" ]
then
    envsubst <"$(1)" >"$(2)"
    exit
fi
if [ ! -e "$(2:%.~out~=%)" ]
then
    touch -d "@0" "$(2:%.~out~=%)"
fi
envsubst <"$(1)" | diff -u "$(2:%.~out~=%)" "-" || true
set +x
echo "WARNING:Template $(1) changed, reconcile and \`$$ touch $(2:%.~out~=%)\`."
set -x
if [ ! -s "$(2:%.~out~=%)" ]
then
    envsubst <"$(1)" >"$(2:%.~out~=%)"
    touch -d "@0" "$(2:%.~out~=%)"
fi
if [ "$(TEMPLATE_IGNORE_EXISTING)" == "true" ]
then
    envsubst <"$(1)" >"$(2)"
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
#     ./var/log/bar.log:
#         mkdir -pv "$(dir $(@))"
#         ./.tox/build/bin/python "./bin/foo.py" | tee -a "$(@)"
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

# TEMPLATE: Run this a single time for your project or when the `./build-host/` image
# changes. See the `./var/log/docker-login*.log` targets for the authentication
# environment variables to set or login to those container registries manually and `$
# touch` these targets.
.PHONY: bootstrap-project
## Run any tasks needed a single time for a given project by a maintainer.
bootstrap-project: ./var/log/docker-login-DOCKER.log
# Initially seed the build host Docker image to bootstrap CI/CD environments
	$(MAKE) -e -C "./build-host/" release
