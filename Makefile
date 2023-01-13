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
CI_REGISTRY_USER=rpatterson

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
PYTHON_ALL_ENVS=$(PYTHON_ENVS) build
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
CI=false
DOCKER_BUILD_ARGS=
DOCKER_REGISTRIES=DOCKER GITLAB GITHUB
export DOCKER_REGISTRY=$(firstword $(DOCKER_REGISTRIES))
DOCKER_IMAGE_DOCKER=$(DOCKER_USER)/python-project-structure
DOCKER_IMAGE_GITLAB=$(CI_REGISTRY_IMAGE)
DOCKER_IMAGE_GITHUB=ghcr.io/$(GITHUB_REPOSITORY_OWNER)/python-project-structure
DOCKER_IMAGE=$(DOCKER_IMAGE_$(DOCKER_REGISTRY))
export DOCKER_VARIANT=
DOCKER_VARIANT_PREFIX=
ifneq ($(DOCKER_VARIANT),)
DOCKER_VARIANT_PREFIX=$(DOCKER_VARIANT)-
endif

# Safe defaults for testing the release process without publishing to the final/official
# hosts/indexes/registries:
BUILD_REQUIREMENTS=true
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
export VCS_BRANCH=$(CI_COMMIT_REF_NAME)
else ifeq ($(GITHUB_ACTIONS),true)
USER_EMAIL=$(USER_NAME)@actions.github.com
export VCS_BRANCH=$(GITHUB_REF_NAME)
else
export VCS_BRANCH:=$(shell git branch --show-current)
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
CI_REGISTRY=registry.gitlab.com/$(CI_REGISTRY_USER)
CI_REGISTRY_IMAGE=$(CI_REGISTRY)/python-project-structure
GITHUB_REPOSITORY_OWNER=$(CI_REGISTRY_USER)
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
build-docker: ./.env ./var/log/host-install.log
ifeq ($(RELEASE_PUBLISH),true)
	if [ -e "./build/next-version.txt" ]
	then
# Ensure the build is made from the version bump commit if it was done elsewhere:
	    git pull --ff-only "origin" "v$$(cat "./build/next-version.txt")"
	fi
endif
# Avoid parallel tox recreations stomping on each other
	$(MAKE) "./var/log/tox/build/build.log"
	$(MAKE) -e -j DOCKER_BUILD_ARGS="--progress plain" \
	    $(PYTHON_MINORS:%=build-docker-%)
.PHONY: $(PYTHON_MINORS:%=build-docker-%)
### Set up for development in a Docker container for one Python version
$(PYTHON_MINORS:%=build-docker-%):
	$(MAKE) -e PYTHON_MINORS="$(@:build-docker-%=%)" \
	    PYTHON_ENV="py$(subst .,,$(@:build-docker-%=%))" \
	    "./var/docker/py$(subst .,,$(@:build-docker-%=%))/log/build.log"
.PHONY: $(DOCKER_REGISTRIES:%=build-docker-tags-%)
### Print the list of image tags for the current registry and variant
$(DOCKER_REGISTRIES:%=build-docker-tags-%):
	docker_image=$(DOCKER_IMAGE_$(@:build-docker-tags-%=%))
	current_version=$$(./.tox/build/bin/cz version --project)
	major_version=$$(echo $${current_version} | sed -nE 's|([0-9]+).*|\1|p')
	minor_version=$$(
	    echo $${current_version} | sed -nE 's|([0-9]+\.[0-9]+).*|\1|p'
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
# Running `$ pip-compile` in parallel generates a lot of network requests so if your
# network connection is intermittent, even rarely, you'll probably see these errors:
#     WARNING: Skipping page https://pypi.org/simple/wheel/ because the GET request got
#     Content-Type: .  The only supported Content-Type is text/html
	$(MAKE) -e -j \
	    "./requirements/$(@:build-requirements-%=%)/user.txt" \
	    "./requirements/$(@:build-requirements-%=%)/devel.txt" \
	    "./requirements/$(@:build-requirements-%=%)/build.txt" \
	    "./requirements/$(@:build-requirements-%=%)/host.txt"

.PHONY: build-wheel
### Build the package/distribution format that is fastest to install
build-wheel: \
		./var/docker/$(PYTHON_ENV)/log/build.log \
		./var/docker/$(PYTHON_ENV)/.tox/$(PYTHON_ENV)/bin/activate
# Retrieve VCS data needed for versioning (tags) and release (release notes)
	git fetch --tags origin "$(VCS_BRANCH)"
	ln -sfv "$$(
	    docker compose run --rm python-project-structure-devel pyproject-build -w |
	    sed -nE 's|^Successfully built (.+\.whl)$$|\1|p'
	)" "./dist/.current.whl"

.PHONY: build-bump
### Bump the package version if on a branch that should trigger a release
build-bump: \
		~/.gitconfig ./var/log/host-install.log \
		./var/docker/$(PYTHON_ENV)/log/build.log \
		./var/docker/$(PYTHON_ENV)/.tox/$(PYTHON_ENV)/bin/activate
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
ifneq ($(CI),true)
# If running under CI/CD then the image will be updated in the next pipeline stage.
# For testing locally, however, ensure the image is up-to-date for subsequent recipes.
	$(MAKE) -e "./var/docker/$(PYTHON_ENV)/log/build.log"
endif
ifeq ($(RELEASE_PUBLISH),true)
# The VCS remote should reflect the release before the release is published to ensure
# that a published release is never *not* reflected in VCS:
	git push -o ci.skip --no-verify --tags \
	    "origin" "v$$(cat "./build/next-version.txt")"
# Ensure the tag is in place on the GitHub mirror so we can create the project host
# release object there:
	git push -o ci.skip --no-verify --tags \
	    "github" "v$$(cat "./build/next-version.txt")"
endif

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
.PHONY: check-clean
### Confirm that the checkout is free of uncommitted VCS changes
check-clean: ./var/log/host-install.log
	if [ -n "$$(git status --porcelain)" ]
	then
	    set +x
	    echo "CRITICAL: Checkout is not clean, not publishing release"
	    false
	fi

.PHONY: release
### Publish installable Python packages to PyPI and container images to Docker Hub
release: release-python
	$(MAKE) -e release-docker

.PHONY: release-python
### Publish installable Python packages to PyPI
release-python: \
		~/.pypirc ./var/log/codecov-install.log ./var/log/host-install.log \
		./.env ./dist/.current.whl
# Upload any build or test artifacts to CI/CD providers
ifeq ($(GITLAB_CI),true)
	codecov --nonZero -t "$(CODECOV_TOKEN)" \
	    --file "./build/$(PYTHON_ENV)/coverage.xml"
endif
ifeq ($(RELEASE_PUBLISH),true)
	if [ -e "./build/next-version.txt" ]
	then
# Ensure the release is made from the version bump commit if it was done elsewhere:
	    git pull --ff-only "origin" "v$$(cat "./build/next-version.txt")"
	fi
# Import the private signing key from CI secrets
	$(MAKE) -e ./var/log/gpg-import.log
endif
# Build Python packages/distributions from the development Docker container for
# consistency/reproducibility.
	docker pull "$(DOCKER_IMAGE):devel-$(PYTHON_ENV)-$(VCS_BRANCH)" || true
	mkdir -pv "./var/docker/$(PYTHON_ENV)/log/"
	touch "./var/docker/$(PYTHON_ENV)/log/build.log"
	$(MAKE) "./var/docker/$(PYTHON_ENV)/.tox/$(PYTHON_ENV)/bin/activate"
	docker compose run --rm python-project-structure-devel pyproject-build -s
# https://twine.readthedocs.io/en/latest/#using-twine
	$(TOX_EXEC_BUILD_ARGS) twine check ./dist/python?project?structure-*
	$(MAKE) "check-clean"
	if [ ! -e "./build/next-version.txt" ]
	then
	    exit
	fi
# Only release from the `master` or `develop` branches:
ifeq ($(RELEASE_PUBLISH),true)
# https://twine.readthedocs.io/en/latest/#using-twine
	$(TOX_EXEC_BUILD_ARGS) twine upload -s -r "$(PYPI_REPO)" \
	    ./dist/python?project?structure-*
	current_version=$$(./.tox/build/bin/cz version --project)
# Create a GitLab release
	./.tox/build/bin/twine upload -s -r "gitlab" ./dist/python?project?structure-*
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
	gh release create "v$${current_version}" $(GITHUB_RELEASE_ARGS) \
	    --notes-file "./NEWS-release.rst" ./dist/python?project?structure-*
endif

.PHONY: release-docker
### Publish all container images to all container registries
release-docker: build-docker
	$(MAKE) -e -j $(PYTHON_MINORS:%=release-docker-%)
.PHONY: $(PYTHON_MINORS:%=release-docker-%)
### Publish the container images for one Python version to all container registry
$(PYTHON_MINORS:%=release-docker-%):
	export PYTHON_ENV="py$(subst .,,$(@:release-docker-%=%))"
	$(MAKE) -e -j $(DOCKER_REGISTRIES:%=release-docker-registry-%)
ifeq ($${PYTHON_ENV},$(PYTHON_LATEST_ENV))
	docker compose run --rm docker-pushrm
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
test-debug: ./var/log/tox/$(PYTHON_ENV)/editable.log
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
		./var/log/docker-login-GITLAB.log \
		./var/log/docker-login-GITHUB.log
# Initially seed the build host Docker image to bootstrap CI/CD environments
# GitLab CI/CD:
	$(MAKE) -C "./build-host/" DOCKER_IMAGE="$(DOCKER_IMAGE_GITLAB)" release
# GitHub Actions:
	$(MAKE) -C "./build-host/" DOCKER_IMAGE="$(DOCKER_IMAGE_GITHUB)" release

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
	$(MAKE) "$(@:requirements/%/devel.txt=./var/log/tox/%/build.log)"
	./.tox/$(@:requirements/%/devel.txt=%)/bin/pip-compile \
	    --resolver "backtracking" $(PIP_COMPILE_ARGS) --extra "devel" \
	    --output-file "$(@)" "$(<)"
	mkdir -pv "./var/log/"
	touch "./var/log/rebuild.log"
$(PYTHON_ENVS:%=./requirements/%/user.txt): ./pyproject.toml ./setup.cfg ./tox.ini
	true DEBUG Updated prereqs: $(?)
	$(MAKE) "$(@:requirements/%/user.txt=./var/log/tox/%/build.log)"
	./.tox/$(@:requirements/%/user.txt=%)/bin/pip-compile \
	    --resolver "backtracking" $(PIP_COMPILE_ARGS) --output-file "$(@)" "$(<)"
	mkdir -pv "./var/log/"
	touch "./var/log/rebuild.log"
$(PYTHON_ENVS:%=./requirements/%/host.txt): ./requirements/host.txt.in
	true DEBUG Updated prereqs: $(?)
	$(MAKE) "$(@:requirements/%/host.txt=./var/log/tox/%/build.log)"
	./.tox/$(@:requirements/%/host.txt=%)/bin/pip-compile \
	    --resolver "backtracking" $(PIP_COMPILE_ARGS) --output-file "$(@)" "$(<)"
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
	$(MAKE) "$(@:requirements/%/build.txt=./var/log/tox/%/build.log)"
	./.tox/$(@:requirements/%/build.txt=%)/bin/pip-compile \
	    --resolver "backtracking" $(PIP_COMPILE_ARGS) --output-file "$(@)" "$(<)"

# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`
$(PYTHON_ALL_ENVS:%=./var/log/tox/%/build.log): ./var/log/host-install.log
	mkdir -pv "$(dir $(@))"
	tox exec $(TOX_EXEC_OPTS) -e "$(@:var/log/tox/%/build.log=%)" -- python -c "" |
	    tee -a "$(@)"
$(PYTHON_ENVS:%=./var/log/tox/%/editable.log):
	$(MAKE) ./var/log/host-install.log
	mkdir -pv "$(dir $(@))"
	tox exec $(TOX_EXEC_OPTS) -e "$(@:var/log/tox/%/editable.log=%)" -- \
	    pip install -e "./" | tee -a "$(@)"

# Build a wheel package but only if one hasn't already been made
./dist/.current.whl:
	$(MAKE) build-wheel

# Docker targets
./var/docker/$(PYTHON_ENV)/log/build.log: \
		./Dockerfile ./Dockerfile.devel ./.dockerignore ./bin/entrypoint \
		./pyproject.toml ./setup.cfg ./tox.ini ./requirements/host.txt.in \
		./docker-compose.yml ./docker-compose.override.yml ./.env \
		./var/log/tox/build/build.log ./var/docker/$(PYTHON_ENV)/log/rebuild.log
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
# Retrieve VCS data needed for versioning (tags) and release (release notes)
	git fetch --tags origin "$(VCS_BRANCH)"
	current_version=$$(./.tox/build/bin/cz version --project)
# https://github.com/moby/moby/issues/39003#issuecomment-879441675
	docker_build_args="$(DOCKER_BUILD_ARGS) \
	    --build-arg BUILDKIT_INLINE_CACHE=1 \
	    --build-arg PYTHON_MINOR=$(PYTHON_MINOR) \
	    --build-arg PYTHON_ENV=$(PYTHON_ENV) \
	    --build-arg VERSION=$${current_version}"
	docker_build_user_tags=""
	for user_tag in $$($(MAKE) -e --no-print-directory build-docker-tags)
	do
	    docker_build_user_tags+="--tag $${user_tag} "
	done
	docker_build_caches=""
ifeq ($(GITLAB_CI),true)
# Don't cache when building final releases on `master`
	$(MAKE) -e "./var/log/docker-login-GITLAB.log"
ifneq ($(VCS_BRANCH),master)
	docker pull "$(DOCKER_IMAGE_GITLAB):$(PYTHON_ENV)-$(VCS_BRANCH)" || true
	docker_build_caches+=" \
	--cache-from $(DOCKER_IMAGE_GITLAB):$(PYTHON_ENV)-$(VCS_BRANCH)"
endif
endif
ifeq ($(GITHUB_ACTIONS),true)
	$(MAKE) -e "./var/log/docker-login-GITHUB.log"
ifneq ($(VCS_BRANCH),master)
# Can't use the GitHub Actions cache when we're only pushing images from GitLab CI/CD
	docker pull "$(DOCKER_IMAGE_GITHUB):$(PYTHON_ENV)-$(VCS_BRANCH)" || true
	docker_build_caches+=" \
	--cache-from $(DOCKER_IMAGE_GITHUB):$(PYTHON_ENV)-$(VCS_BRANCH)"
endif
endif
# This variant is the default used for tags such as `latest`
	docker buildx build --pull $${docker_build_args} $${docker_build_user_tags} \
	    $${docker_build_caches} "./"
# Ensure any subsequent builds have optimal caches
ifeq ($(GITLAB_CI),true)
	docker push "$(DOCKER_IMAGE_GITLAB):$(PYTHON_ENV)-$(VCS_BRANCH)"
endif
ifeq ($(GITHUB_ACTIONS),true)
	docker push "$(DOCKER_IMAGE_GITHUB):$(PYTHON_ENV)-$(VCS_BRANCH)"
endif
# Build the development image
	docker_build_devel_tags=""
	for devel_tag in $$(
	    $(MAKE) -e DOCKER_VARIANT="devel" --no-print-directory build-docker-tags
	)
	do
	    docker_build_devel_tags+="--tag $${devel_tag} "
	done
	docker_build_caches=""
ifeq ($(GITLAB_CI),true)
ifneq ($(VCS_BRANCH),master)
	docker pull "$(DOCKER_IMAGE_GITLAB):devel-$(PYTHON_ENV)-$(VCS_BRANCH)" || true
	docker_build_caches+=" --cache-from \
	$(DOCKER_IMAGE_GITLAB):devel-$(PYTHON_ENV)-$(VCS_BRANCH)"
endif
endif
ifeq ($(GITHUB_ACTIONS),true)
ifneq ($(VCS_BRANCH),master)
	docker pull "$(DOCKER_IMAGE_GITHUB):devel-$(PYTHON_ENV)-$(VCS_BRANCH)" || true
	docker_build_caches+=" --cache-from \
	$(DOCKER_IMAGE_GITHUB):devel-$(PYTHON_ENV)-$(VCS_BRANCH)"
endif
endif
	docker buildx build $${docker_build_args} $${docker_build_devel_tags} \
	    $${docker_build_caches} --file "./Dockerfile.devel" "./"
# Ensure any subsequent builds have optimal caches
ifeq ($(GITLAB_CI),true)
	docker push "$(DOCKER_IMAGE_GITLAB):devel-$(PYTHON_ENV)-$(VCS_BRANCH)"
endif
ifeq ($(GITHUB_ACTIONS),true)
	docker push "$(DOCKER_IMAGE_GITHUB):devel-$(PYTHON_ENV)-$(VCS_BRANCH)"
endif
	date >>"$(@)"
# The image installs the host requirements, reflect that in the bind mount volumes
	date >>"$(@:%/build.log=%/host-install.log)"
# Update the pinned/frozen versions, if needed, using the container.  If changed, then
# we may need to re-build the container image again to ensure it's current and correct.
ifeq ($(BUILD_REQUIREMENTS),true)
	docker compose run --rm -T python-project-structure-devel \
	    make -e PYTHON_MINORS="$(PYTHON_MINOR)" build-requirements-$(PYTHON_ENV)
	$(MAKE) -e "$(@)"
endif
# Marker file used to trigger the rebuild of the image for just one Python version.
# Useful to workaround async timestamp issues when running jobs in parallel.
./var/docker/$(PYTHON_ENV)/log/rebuild.log:
	mkdir -pv "$(dir $(@))"
	date >>"$(@)"
# Target for use as a prerequisite in host targets that depend on the virtualenv having
# been built.
$(PYTHON_ALL_ENVS:%=./var/docker/%/.tox/%/bin/activate):
	python_env=$(notdir $(@:%/bin/activate=%))
	$(MAKE) "./var/docker/$${python_env}/log/build.log"
	docker compose run --rm -T python-project-structure-devel \
	    make -e PYTHON_MINORS="$(PYTHON_MINOR)" \
	    "./var/log/tox/$${python_env}/build.log"

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

./var/log/docker-login-DOCKER.log: ./.env
	mkdir -pv "$(dir $(@))"
	set +x
	source "./.env"
	export DOCKER_PASS
	printenv "DOCKER_PASS" | docker login -u "merpatterson" --password-stdin
	date | tee -a "$(@)"
./var/log/docker-login-GITLAB.log: ./.env
	mkdir -pv "$(dir $(@))"
	set +x
	source "./.env"
	printenv "CI_REGISTRY_PASSWORD" |
	    docker login -u "$(CI_REGISTRY_USER)" --password-stdin "$(CI_REGISTRY)"
	date | tee -a "$(@)"
./var/log/docker-login-GITHUB.log: ./.env
	mkdir -pv "$(dir $(@))"
	set +x
	source "./.env"
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
