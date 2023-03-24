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
export DOCKER_USER=merpatterson

# Values derived from the environment
USER_NAME:=$(shell id -u -n)
USER_FULL_NAME:=$(shell \
    getent passwd "$(USER_NAME)" | cut -d ":" -f 5 | cut -d "," -f 1 \
)
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
# Use the same Python version tox would as a default:
# https://tox.wiki/en/latest/config.html#base_python
PYTHON_HOST_MINOR:=$(shell \
    pip --version | sed -nE 's|.* \(python ([0-9]+.[0-9]+)\)$$|\1|p' \
)
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
export DOCKER_GID=$(shell getent group "docker" | cut -d ":" -f 3)

# Values derived from constants
# Support passing in the Python versions to test, including testing one version:
#     $ make PYTHON_MINORS=3.11 test
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
CI=false
DOCKER_COMPOSE_RUN_ARGS=--rm
ifneq ($(CI),true)
DOCKER_COMPOSE_RUN_ARGS+= --quiet-pull
endif
DOCKER_BUILD_ARGS=
DOCKER_REGISTRIES=DOCKER
export DOCKER_REGISTRY=$(firstword $(DOCKER_REGISTRIES))
DOCKER_IMAGE_DOCKER=$(DOCKER_USER)/python-project-structure
DOCKER_IMAGE=$(DOCKER_IMAGE_$(DOCKER_REGISTRY))
export DOCKER_VARIANT=
DOCKER_VARIANT_PREFIX=
ifneq ($(DOCKER_VARIANT),)
DOCKER_VARIANT_PREFIX=$(DOCKER_VARIANT)-
endif
DOCKER_VOLUMES=\
./var/ ./var/docker/$(PYTHON_ENV)/ \
./src/python_project_structure.egg-info/ \
./var/docker/$(PYTHON_ENV)/python_project_structure.egg-info/ \
./.tox/ ./var/docker/$(PYTHON_ENV)/.tox/


# Safe defaults for testing the release process without publishing to the final/official
# hosts/indexes/registries:
BUILD_REQUIREMENTS=true
RELEASE_PUBLISH=false
TOWNCRIER_COMPARE_BRANCH=develop
PYPI_REPO=testpypi
# Only publish releases from the `master` or `develop` branches:
export VCS_BRANCH:=$(shell git branch --show-current)
ifeq ($(VCS_BRANCH),master)
RELEASE_PUBLISH=true
TOWNCRIER_COMPARE_BRANCH=master
PYPI_REPO=pypi
else ifeq ($(VCS_BRANCH),develop)
# Publish pre-releases from the `develop` branch:
RELEASE_PUBLISH=true
PYPI_REPO=pypi
endif

# Makefile functions
current_pkg = $(shell ls -t ./dist/*$(1) | head -n 1)

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
build-docker: build-pkgs
	$(MAKE) -e -j PYTHON_WHEEL="$(call current_pkg,.whl)" \
	    DOCKER_BUILD_ARGS="--progress plain" \
	    $(PYTHON_MINORS:%=build-docker-%)
.PHONY: $(PYTHON_MINORS:%=build-docker-%)
### Set up for development in a Docker container for one Python version
$(PYTHON_MINORS:%=build-docker-%):
	$(MAKE) -e \
	    PYTHON_MINORS="$(@:build-docker-%=%)" \
	    PYTHON_MINOR="$(@:build-docker-%=%)" \
	    PYTHON_ENV="py$(subst .,,$(@:build-docker-%=%))" \
	    "./var/docker/py$(subst .,,$(@:build-docker-%=%))/log/build-user.log"
.PHONY: $(DOCKER_REGISTRIES:%=build-docker-tags-%)
### Print the list of image tags for the current registry and variant
$(DOCKER_REGISTRIES:%=build-docker-tags-%):
	docker_image=$(DOCKER_IMAGE_$(@:build-docker-tags-%=%))
	export VERSION=$$(./.tox/build/bin/cz version --project)
	major_version=$$(echo $${VERSION} | sed -nE 's|([0-9]+).*|\1|p')
	minor_version=$$(
	    echo $${VERSION} | sed -nE 's|([0-9]+\.[0-9]+).*|\1|p'
	)
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)-$(VCS_BRANCH)
ifeq ($(VCS_BRANCH),master)
# Only update tags end users may depend on to be stable from the `master` branch
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)-$${minor_version}
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)-$${major_version}
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(PYTHON_ENV)
endif
# This variant is the default used for tags such as `latest`
ifeq ($(PYTHON_ENV),$(PYTHON_LATEST_ENV))
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(VCS_BRANCH)
ifeq ($(VCS_BRANCH),master)
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$${minor_version}
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$${major_version}
ifeq ($(DOCKER_VARIANT),)
	echo $${docker_image}:latest
else
	echo $${docker_image}:$(DOCKER_VARIANT)
endif
endif
endif
.PHONY: build-docker-tags
### Print the list of image tags for the current registry and variant
build-docker-tags:
	$(MAKE) $(DOCKER_REGISTRIES:%=build-docker-tags-%)

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

.PHONY: $(PYTHON_MINORS:%=build-docker-requirements-%)
### Pull container images and compile fixed/pinned dependency versions if necessary
$(PYTHON_MINORS:%=build-docker-requirements-%): ./.env
	export PYTHON_MINOR="$(@:build-docker-requirements-%=%)"
	export PYTHON_ENV="py$(subst .,,$(@:build-docker-requirements-%=%))"
	$(MAKE) build-docker-volumes-$${PYTHON_ENV}
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) -T \
	    python-project-structure-devel make -e \
	    PYTHON_MINORS="$(@:build-docker-requirements-%=%)" \
	    build-requirements-py$(subst .,,$(@:build-docker-requirements-%=%))

.PHONY: build-docker-pull
### Pull the development image and simulate as if it had been built here
build-docker-pull: ./.env build-docker-volumes-$(PYTHON_ENV) \
		./var/log/tox/build/build.log
	export VERSION=$$(./.tox/build/bin/cz version --project)
	if docker compose pull --quiet python-project-structure-devel
	then
	    mkdir -pv "./var/docker/$(PYTHON_ENV)/log/"
	    touch "./var/docker/$(PYTHON_ENV)/log/build-devel.log" \
	        "./var/docker/$(PYTHON_ENV)/log/rebuild.log"
	    $(MAKE) -e "./var/docker/$(PYTHON_ENV)/.tox/$(PYTHON_ENV)/bin/activate"
	else
	    $(MAKE) "./var/docker/$(PYTHON_ENV)/log/build-devel.log"
	fi

.PHONY: build-pkgs
### Ensure the built package is current when used outside of tox
build-pkgs: build-docker-volumes-$(PYTHON_ENV) build-docker-pull
# Defined as a .PHONY recipe so that multiple targets can depend on this as a
# pre-requisite and it will only be run once per invocation.
	mkdir -pv "./dist/"
# Build Python packages/distributions from the development Docker container for
# consistency/reproducibility.
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) -T \
	    python-project-structure-devel tox run -e "$(PYTHON_ENV)" --pkg-only
# Copy the wheel to a location accessible to all containers:
	cp -lfv "$$(
	    ls -t ./var/docker/$(PYTHON_ENV)/.tox/.pkg/dist/*.whl | head -n 1
	)" "./dist/"
# Also build the source distribution:
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) -T \
	    python-project-structure-devel \
	    tox run -e "$(PYTHON_ENV)" --override "testenv.package=sdist" --pkg-only
	cp -lfv "$$(
	    ls -t ./var/docker/$(PYTHON_ENV)/.tox/.pkg/dist/*.tar.gz | head -n 1
	)" "./dist/"

.PHONY: build-bump
### Bump the package version if on a branch that should trigger a release
build-bump: ~/.gitconfig ./var/log/tox/build/build.log \
		build-docker-volumes-$(PYTHON_ENV) build-docker-pull
# Retrieve VCS data needed for versioning (tags) and release (release notes)
	git_fetch_args=--tags
	if [ "$$(git rev-parse --is-shallow-repository)" == "true" ]
	then
	    git_fetch_args+=" --unshallow"
	fi
	git fetch $${git_fetch_args} origin "$(TOWNCRIER_COMPARE_BRANCH)"
# Check if the conventional commits since the last release require new release and thus
# a version bump:
	if ! $(TOX_EXEC_BUILD_ARGS) python ./bin/cz-check-bump
	then
	    exit
	fi
# Collect the versions involved in this release according to conventional commits:
	cz_bump_args="--check-consistency --no-verify"
ifneq ($(VCS_BRANCH),master)
	cz_bump_args+=" --prerelease beta"
endif
# Update the release notes/changelog
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) python-project-structure-devel \
	    $(TOX_EXEC_ARGS) \
	    towncrier check --compare-with "origin/$(TOWNCRIER_COMPARE_BRANCH)"
	if ! git diff --cached --exit-code
	then
	    set +x
	    echo "CRITICAL: Cannot bump version with staged changes"
	    false
	fi
ifeq ($(RELEASE_PUBLISH),true)
# Build and stage the release notes to be commited by `$ cz bump`
	next_version=$$(
	    $(TOX_EXEC_BUILD_ARGS) cz bump $${cz_bump_args} --yes --dry-run |
	    sed -nE 's|.* ([^ ]+) *→ *([^ ]+).*|\2|p'
	) || true
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
ifneq ($(CI),true)
# If running under CI/CD then the image will be updated in the next pipeline stage.
# For testing locally, however, ensure the image is up-to-date for subsequent recipes.
	$(MAKE) -e "./var/docker/$(PYTHON_ENV)/log/build-user.log"
endif
# The VCS remote should reflect the release before the release is published to ensure
# that a published release is never *not* reflected in VCS.
	git push --no-verify --tags "origin" "HEAD:$(VCS_BRANCH)"
endif

.PHONY: start
### Run the local development end-to-end stack services in the background as daemons
start: build-docker-volumes-$(PYTHON_ENV) build-docker-$(PYTHON_MINOR) ./.env
	docker compose down
	docker compose up -d
.PHONY: run
### Run the local development end-to-end stack services in the foreground for debugging
run: build-docker-volumes-$(PYTHON_ENV) build-docker-$(PYTHON_MINOR) ./.env
	docker compose down
	docker compose up

.PHONY: check-push
### Perform any checks that should only be run before pushing
check-push: build-docker-volumes-$(PYTHON_ENV) build-docker-$(PYTHON_MINOR) ./.env
	if $(TOX_EXEC_BUILD_ARGS) python ./bin/cz-check-bump
	then
	    docker compose run $(DOCKER_COMPOSE_RUN_ARGS) \
	        python-project-structure-devel $(TOX_EXEC_ARGS) \
	        towncrier check --compare-with "origin/$(TOWNCRIER_COMPARE_BRANCH)"
	fi
.PHONY: check-clean
### Confirm that the checkout is free of uncommitted VCS changes
check-clean:
	if [ -n "$$(git status --porcelain)" ]
	then
	    set +x
	    echo "Checkout is not clean"
	    false
	fi

.PHONY: release
### Publish installable Python packages to PyPI and container images to Docker Hub
release: release-python release-docker

.PHONY: release-python
### Publish installable Python packages to PyPI
release-python: ./var/log/tox/build/build.log build-pkgs ~/.pypirc
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

.PHONY: release-docker
### Publish all container images to all container registries
release-docker: build-docker-volumes-$(PYTHON_ENV) build-docker \
		$(DOCKER_REGISTRIES:%=./var/log/docker-login-%.log)
	$(MAKE) -e -j $(PYTHON_MINORS:%=release-docker-%)
.PHONY: $(PYTHON_MINORS:%=release-docker-%)
### Publish the container images for one Python version to all container registry
$(PYTHON_MINORS:%=release-docker-%): $(DOCKER_REGISTRIES:%=./var/log/docker-login-%.log)
	export PYTHON_ENV="py$(subst .,,$(@:release-docker-%=%))"
	$(MAKE) -e -j $(DOCKER_REGISTRIES:%=release-docker-registry-%)
ifeq ($${PYTHON_ENV},$(PYTHON_LATEST_ENV))
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) docker-pushrm
endif
.PHONY: $(DOCKER_REGISTRIES:%=release-docker-registry-%)
### Publish all container images to one container registry
$(DOCKER_REGISTRIES:%=release-docker-registry-%):
# https://docs.docker.com/docker-hub/#step-5-build-and-push-a-container-image-to-docker-hub-from-your-computer
	$(MAKE) "./var/log/docker-login-$(@:release-docker-registry-%=%).log"
	for user_tag in $$(
	    $(MAKE) -e --no-print-directory \
	        build-docker-tags-$(@:release-docker-registry-%=%)
	)
	do
	    docker push "$${user_tag}"
	done
	for devel_tag in $$(
	    $(MAKE) -e DOCKER_VARIANT="devel" --no-print-directory \
	        build-docker-tags-$(@:release-docker-registry-%=%)
	)
	do
	    docker push "$${devel_tag}"
	done

.PHONY: format
### Automatically correct code in this checkout according to linters and style checkers
format:  ./var/log/tox/$(PYTHON_ENV)/build.log
	$(TOX_EXEC_ARGS) autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables "./src/pythonprojectstructure/"
	$(TOX_EXEC_ARGS) autopep8 -v -i -r "./src/pythonprojectstructure/"
	$(TOX_EXEC_ARGS) black "./src/pythonprojectstructure/"

.PHONY: lint-docker
### Check the style and content of the `./Dockerfile*` files
lint-docker: ./.env build-docker-volumes-$(PYTHON_ENV)
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) hadolint \
	    hadolint "./Dockerfile"
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) hadolint \
	    hadolint "./Dockerfile.devel"
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) hadolint \
	    hadolint "./build-host/Dockerfile"

.PHONY: test
### Format the code and run the full suite of tests, coverage checks, and linters
test: lint-docker test-docker
.PHONY: test-docker
### Format the code and run the full suite of tests, coverage checks, and linters
test-docker: build-pkgs
	$(MAKE) -e -j PYTHON_WHEEL="$(call current_pkg,.whl)" \
	    DOCKER_BUILD_ARGS="--progress plain" \
	    $(PYTHON_MINORS:%=test-docker-%)
.PHONY: $(PYTHON_MINORS:%=test-docker-%)
### Run the full suite of tests inside a docker container for this Python version
$(PYTHON_MINORS:%=test-docker-%):
	$(MAKE) -e \
	    PYTHON_MINORS="$(@:test-docker-%=%)" \
	    PYTHON_MINOR="$(@:test-docker-%=%)" \
	    PYTHON_ENV="py$(subst .,,$(@:test-docker-%=%))" \
	    test-docker-pyminor
.PHONY: test-docker-pyminor
test-docker-pyminor: build-docker-volumes-$(PYTHON_ENV) build-docker-$(PYTHON_MINOR)
	docker_run_args="--rm"
	if [ ! -t 0 ]
	then
# No fancy output when running in parallel
	    docker_run_args+=" -T"
	fi
# Ensure the dist/package has been correctly installed in the image
	docker compose run --no-deps $${docker_run_args} python-project-structure \
	    python -c 'import pythonprojectstructure; print(pythonprojectstructure)'
# Run from the development Docker container for consistency
	docker compose run $${docker_run_args} python-project-structure-devel \
	    make -e PYTHON_MINORS="$(PYTHON_MINORS)" PYTHON_WHEEL="$(PYTHON_WHEEL)" \
	        test-local
.PHONY: test-local
### Run the full suite of tests on the local host
test-local:
	tox $(TOX_RUN_ARGS) -e "$(TOX_ENV_LIST)"
.PHONY: test-debug
### Run tests in the main/default environment and invoke the debugger on errors/failures
test-debug: ./var/log/tox/$(PYTHON_ENV)/editable.log
	$(TOX_EXEC_ARGS) pytest --pdb

.PHONY: upgrade
### Update all fixed/pinned dependencies to their latest available versions
upgrade: ./.env build-docker-volumes-$(PYTHON_ENV)
	touch "./setup.cfg" "./requirements/build.txt.in" \
	    "./build-host/requirements.txt.in"
ifeq ($(CI),true)
# Pull separately to reduce noisy interactive TTY output where it shouldn't be:
	docker compose pull --quiet python-project-structure-devel
endif
	docker compose create python-project-structure-devel
# Ensure the network is create first to avoid race conditions
	docker compose create python-project-structure-devel
	$(MAKE) -e -j $(PYTHON_MINORS:%=build-docker-requirements-%)
# Update VCS hooks from remotes to the latest tag.
	$(TOX_EXEC_BUILD_ARGS) pre-commit autoupdate
.PHONY: upgrade-branch
### Reset an upgrade branch, commit upgraded dependencies on it, and push for review
upgrade-branch: ~/.gitconfig
	git fetch "origin" "$(VCS_BRANCH)"
	remote_branch_exists=false
	if git fetch "origin" "$(VCS_BRANCH)-upgrade"
	then
	    remote_branch_exists=true
	fi
	if git show-ref -q --heads "$(VCS_BRANCH)-upgrade"
	then
# Reset an existing local branch to the latest upstream before upgrading
	    git checkout "$(VCS_BRANCH)-upgrade"
	    git reset --hard "origin/$(VCS_BRANCH)"
	else
# Create a new local branch from the latest upstream before upgrading
	    git checkout -b "$(VCS_BRANCH)-upgrade" "origin/$(VCS_BRANCH)"
	fi
	now=$$(date -u)
	$(MAKE) TEMPLATE_IGNORE_EXISTING="true" upgrade
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
	    git_push_args+=" \
	        --force-with-lease=$(VCS_BRANCH)-upgrade:origin/$(VCS_BRANCH)-upgrade"
	fi
	git push $${git_push_args} "origin" "HEAD:$(VCS_BRANCH)-upgrade"

# TEMPLATE: Run this once for your project.  See the `./var/log/docker-login*.log`
# targets for the authentication environment variables that need to be set or just login
# to those container registries manually and touch these targets.
.PHONY: bootstrap-project
### Run any tasks needed to be run once for a given project by a maintainer
bootstrap-project: ./var/log/docker-login-DOCKER.log
# Initially seed the build host Docker image to bootstrap CI/CD environments
	$(MAKE) -C "./build-host/" release

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
	mkdir -pv "./var/log/"
	touch "./var/log/rebuild.log"
$(PYTHON_ENVS:%=./requirements/%/user.txt): ./pyproject.toml ./setup.cfg ./tox.ini
	true DEBUG Updated prereqs: $(?)
	$(MAKE) "$(@:requirements/%/user.txt=./var/log/tox/%/build.log)"
	./.tox/$(@:requirements/%/user.txt=%)/bin/pip-compile \
	    --resolver "backtracking" --upgrade --output-file "$(@)" "$(<)"
	mkdir -pv "./var/log/"
	touch "./var/log/rebuild.log"
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
	mkdir -pv "./var/log/"
	touch "./var/log/rebuild.log"
$(PYTHON_ENVS:%=./requirements/%/build.txt): ./requirements/build.txt.in
	true DEBUG Updated prereqs: $(?)
	$(MAKE) "$(@:requirements/%/build.txt=./var/log/tox/%/build.log)"
	./.tox/$(@:requirements/%/build.txt=%)/bin/pip-compile \
	    --resolver "backtracking" --upgrade --output-file "$(@)" "$(<)"

$(PYTHON_ALL_ENVS:%=./var/log/tox/%/build.log):
	$(MAKE) "$(HOME)/.local/var/log/python-project-structure-host-install.log"
	mkdir -pv "$(dir $(@))"
	tox run $(TOX_EXEC_OPTS) -e "$(@:var/log/tox/%/build.log=%)" --notest |
	    tee -a "$(@)"
# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`
$(PYTHON_ENVS:%=./var/log/tox/%/editable.log):
	$(MAKE) "$(HOME)/.local/var/log/python-project-structure-host-install.log"
	mkdir -pv "$(dir $(@))"
	tox exec $(TOX_EXEC_OPTS) -e "$(@:var/log/tox/%/editable.log=%)" -- \
	    pip install -e "./" | tee -a "$(@)"

# Docker targets
# Build the development image:
./var/docker/$(PYTHON_ENV)/log/build-devel.log: \
		./Dockerfile.devel ./.dockerignore ./bin/entrypoint \
		./pyproject.toml ./setup.cfg ./tox.ini \
		./build-host/requirements.txt.in ./docker-compose.yml \
		./docker-compose.override.yml ./.env \
		./var/docker/$(PYTHON_ENV)/log/rebuild.log
	true DEBUG Updated prereqs: $(?)
	$(MAKE) build-docker-volumes-$(PYTHON_ENV) "./var/log/tox/build/build.log"
	mkdir -pv "$(dir $(@))"
	export VERSION=$$(./.tox/build/bin/cz version --project)
# https://github.com/moby/moby/issues/39003#issuecomment-879441675
	docker_build_args="$(DOCKER_BUILD_ARGS) \
	    --build-arg BUILDKIT_INLINE_CACHE=1 \
	    --build-arg PYTHON_MINOR=$(PYTHON_MINOR) \
	    --build-arg PYTHON_ENV=$(PYTHON_ENV) \
	    --build-arg VERSION=$${VERSION}"
ifeq ($(CI),true)
# Workaround broken interactive session detection
	docker pull "python:${PYTHON_MINOR}"
endif
	docker_build_devel_tags=""
	for devel_tag in $$(
	    $(MAKE) -e DOCKER_VARIANT="devel" --no-print-directory build-docker-tags
	)
	do
	    docker_build_devel_tags+="--tag $${devel_tag} "
	done
	docker buildx build --pull $${docker_build_args} $${docker_build_devel_tags} \
	    --file "./Dockerfile.devel" "./"
	date >>"$(@)"
# Update the pinned/frozen versions, if needed, using the container.  If changed, then
# we may need to re-build the container image again to ensure it's current and correct.
ifeq ($(BUILD_REQUIREMENTS),true)
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) -T \
	    python-project-structure-devel make -e PYTHON_MINORS="$(PYTHON_MINOR)" \
	    build-requirements-$(PYTHON_ENV)
	$(MAKE) -e "$(@)"
endif
# Build the end-user image:
./var/docker/$(PYTHON_ENV)/log/build-user.log: \
		./var/docker/$(PYTHON_ENV)/log/build-devel.log ./Dockerfile \
		./var/docker/$(PYTHON_ENV)/log/rebuild.log
	true DEBUG Updated prereqs: $(?)
	$(MAKE) "./var/log/tox/build/build.log"
	mkdir -pv "$(dir $(@))"
	export VERSION=$$(./.tox/build/bin/cz version --project)
# https://github.com/moby/moby/issues/39003#issuecomment-879441675
	docker_build_args="$(DOCKER_BUILD_ARGS) \
	    --build-arg BUILDKIT_INLINE_CACHE=1 \
	    --build-arg PYTHON_MINOR=$(PYTHON_MINOR) \
	    --build-arg PYTHON_ENV=$(PYTHON_ENV) \
	    --build-arg VERSION=$${VERSION}"
# Build the end-user image now that all required artifacts are built"
ifeq ($(PYTHON_WHEEL),)
	$(MAKE) -e "build-pkgs"
	PYTHON_WHEEL="$$(ls -t ./dist/*.whl | head -n 1)"
endif
	docker_build_user_tags=""
	for user_tag in $$($(MAKE) -e --no-print-directory build-docker-tags)
	do
	    docker_build_user_tags+="--tag $${user_tag} "
	done
	docker buildx build --pull $${docker_build_args} $${docker_build_user_tags} \
	    --build-arg PYTHON_WHEEL="$${PYTHON_WHEEL}" "./"
	date >>"$(@)"
# The image installs the host requirements, reflect that in the bind mount volumes
	date >>"$(@:%/build.log=%/host-install.log)"

.PHONY: $(PYTHON_ENVS:%=build-docker-volumes-%)
### Ensure access permissions to build artifacts in Python version container volumes
# If created by `# dockerd`, they end up owned by `root`.
$(PYTHON_ENVS:%=build-docker-volumes-%): \
		./var/ ./src/python_project_structure.egg-info/ ./.tox/
	$(MAKE) \
	    $(@:build-docker-volumes-%=./var/docker/%/) \
	    $(@:build-docker-volumes-%=./var/docker/%/python_project_structure.egg-info/) \
	    $(@:build-docker-volumes-%=./var/docker/%/.tox/)
./var/ $(PYTHON_ENVS:%=./var/docker/%/) \
./src/python_project_structure.egg-info/ \
$(PYTHON_ENVS:%=./var/docker/%/python_project_structure.egg-info/) \
./.tox/ $(PYTHON_ENVS:%=./var/docker/%/.tox/):
	mkdir -pv "$(@)"

# Marker file used to trigger the rebuild of the image for just one Python version.
# Useful to workaround async timestamp issues when running jobs in parallel.
./var/docker/$(PYTHON_ENV)/log/rebuild.log:
	mkdir -pv "$(dir $(@))"
	date >>"$(@)"

# Target for use as a prerequisite in host targets that depend on the virtualenv having
# been built.
$(PYTHON_ALL_ENVS:%=./var/docker/%/.tox/%/bin/activate):
	python_env=$(notdir $(@:%/bin/activate=%))
	$(MAKE) build-docker-volumes-$(PYTHON_ENV) \
	    "./var/docker/$${python_env}/log/build-devel.log"
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) -T \
	    python-project-structure-devel make -e PYTHON_MINORS="$(PYTHON_MINOR)" \
	    "./var/log/tox/$${python_env}/build.log"

# Local environment variables from a template
./.env: ./.env.in
	$(MAKE) -e "template=$(<)" "target=$(@)" expand-template

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
	$(MAKE) "./var/log/tox/build/build.log"
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

./var/log/docker-login-DOCKER.log: ./.env
	mkdir -pv "$(dir $(@))"
	set +x
	source "./.env"
	export DOCKER_PASS
	set -x
	printenv "DOCKER_PASS" | docker login -u "merpatterson" --password-stdin
	date | tee -a "$(@)"
