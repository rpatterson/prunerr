# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

## Development, build and maintenance tasks:
#
# To ease discovery for new contributors, variables that act as options affecting
# behavior are at the top.  Then skip to `## Top-level targets:` below to find targets
# intended for use by developers.  The real work, however, is in the recipes for real
# targets that follow.  If making changes here, please start by reading the philosophy
# commentary at the bottom of this file.

# Project specific values:
export PROJECT_NAMESPACE=rpatterson
export PROJECT_NAME=project-structure

# Variables used as options to control behavior:
export TEMPLATE_IGNORE_EXISTING=false
export DOCKER_USER=merpatterson


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

# Values derived from VCS/git:
VCS_LOCAL_BRANCH:=$(shell git branch --show-current)
VCS_TAG=
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
# Determine the best remote and branch for release data, e.g. conventional commits:
VCS_COMPARE_REMOTE=$(VCS_UPSTREAM_REMOTE)
ifeq ($(VCS_COMPARE_REMOTE),)
VCS_COMPARE_REMOTE=$(VCS_PUSH_REMOTE)
endif
VCS_COMPARE_BRANCH=$(VCS_UPSTREAM_BRANCH)
ifeq ($(VCS_COMPARE_BRANCH),)
VCS_COMPARE_BRANCH=$(VCS_BRANCH)
endif
# If pushing to upstream release branches, get release data compared to the previous
# release:
ifeq ($(VCS_COMPARE_BRANCH),develop)
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

# Run Python tools in isolated environments managed by Tox:
TOX_EXEC_OPTS=--no-recreate-pkg --skip-pkg-install
TOX_EXEC_BUILD_ARGS=tox exec $(TOX_EXEC_OPTS) -e "build"

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
# Safe defaults for testing the release process without publishing to the final/official
# hosts/indexes/registries:
RELEASE_PUBLISH=false
# Only publish releases from the `main` or `develop` branches:
ifeq ($(VCS_BRANCH),main)
RELEASE_PUBLISH=true
else ifeq ($(VCS_BRANCH),develop)
# Publish pre-releases from the `develop` branch:
RELEASE_PUBLISH=true
endif
DOCKER_PLATFORMS=
ifeq ($(RELEASE_PUBLISH),true)
# TEMPLATE: Choose the platforms on which your end-users need to be able to run the
# image.  These default platforms should cover most common end-user platforms, including
# modern Apple M1 CPUs, Raspberry Pi devices, etc.:
DOCKER_PLATFORMS=linux/amd64 linux/arm64 linux/arm/v7
endif

# Override variable values if present in `./.env` and if not overridden on the CLI:
include $(wildcard .env)

# Done with `$(shell ...)`, echo recipe commands going forward
.SHELLFLAGS+= -x


## Top-level targets:

.PHONY: all
### The default target.
all: build

.PHONY: start
### Run the local development end-to-end stack services in the background as daemons.
start: build-docker ./.env.~out~
	docker compose down
	docker compose up -d

.PHONY: run
### Run the local development end-to-end stack services in the foreground for debugging.
run: build-docker ./.env.~out~
	docker compose down
	docker compose up


## Build Targets:
#
# Recipes that make artifacts needed for by end-users, development tasks, other recipes.

.PHONY: build
### Set up everything for development from a checkout, local and in containers.
build: ./.git/hooks/pre-commit ./.env.~out~ \
		$(HOME)/.local/var/log/$(PROJECT_NAME)-host-install.log \
		build-docker

.PHONY: build-pkgs
### Ensure the built package is current.
build-pkgs: ./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH) \
		./var-docker/log/build-devel.log
	true "TEMPLATE: Always specific to the type of project"

## Docker Build Targets:
#
# Strive for as much consistency as possible in development tasks between the local host
# and inside containers.  To that end, most of the `*-docker` container target recipes
# should run the corresponding `*-local` local host target recipes inside the
# development container.  Top level targets, like `test`, should run as much as possible
# inside the development container.

.PHONY: build-docker
### Set up for development in Docker containers.
build-docker: build-pkgs ./var-docker/log/build-user.log

.PHONY: build-docker-tags
### Print the list of image tags for the current registry and variant.
build-docker-tags:
	$(MAKE) -e $(DOCKER_REGISTRIES:%=build-docker-tags-%)

.PHONY: $(DOCKER_REGISTRIES:%=build-docker-tags-%)
### Print the list of image tags for the current registry and variant.
$(DOCKER_REGISTRIES:%=build-docker-tags-%):
	test -e "./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH)"
	docker_image=$(DOCKER_IMAGE_$(@:build-docker-tags-%=%))
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)$(DOCKER_BRANCH_TAG)
ifeq ($(VCS_BRANCH),main)
# Only update tags end users may depend on to be stable from the `main` branch
	VERSION=$$($(TOX_EXEC_BUILD_ARGS) -qq -- cz version --project)
	major_version=$$(echo $${VERSION} | sed -nE 's|([0-9]+).*|\1|p')
	minor_version=$$(
	    echo $${VERSION} | sed -nE 's|([0-9]+\.[0-9]+).*|\1|p'
	)
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)v$${minor_version}
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)v$${major_version}
	echo $${docker_image}:$(DOCKER_VARIANT_PREFIX)
endif
# This variant is the default used for tags such as `latest`
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

.PHONY: build-docker-build
### Run the actual commands used to build the Docker container image.
build-docker-build: ./Dockerfile \
		$(HOME)/.local/var/log/docker-multi-platform-host-install.log \
		./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH) \
		./var/log/docker-login-DOCKER.log
# Workaround broken interactive session detection:
	docker pull "buildpack-deps"
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
	    --build-arg VERSION="$$(
	        $(TOX_EXEC_BUILD_ARGS) -qq -- cz version --project
	    )" \
	    $${docker_build_args} --file "$(<)" "./"


## Test Targets:
#
# Recipes that run the test suite.

.PHONY: test
### Format the code and run the full suite of tests, coverage checks, and linters.
test: test-lint test-docker-lint test-docker

.PHONY: test-local
### Run the full suite of tests, coverage checks, and linters.
test-local:
	true "TEMPLATE: Always specific to the type of project"

.PHONY: test-lint
### Perform any linter or style checks, including non-code checks.
test-lint: $(HOME)/.local/var/log/$(PROJECT_NAME)-host-install.log
# Run non-code checks, e.g. documentation:
	tox run -e "build"

.PHONY: test-debug
### Run tests directly on the host and invoke the debugger on errors/failures.
test-debug:
	true "TEMPLATE: Always specific to the type of project"

.PHONY: test-docker
### Run the full suite of tests, coverage checks, and code linters in containers.
test-docker: build-pkgs
	docker_run_args="--rm"
	if [ ! -t 0 ]
	then
# No fancy output when running in parallel
	    docker_run_args+=" -T"
	fi
# Ensure the end-user image runs successfully:
	docker compose run --no-deps $${docker_run_args} $(PROJECT_NAME) true
# Run from the development Docker container for consistency:
	docker compose run $${docker_run_args} $(PROJECT_NAME)-devel \
	    make -e test-local

.PHONY: test-docker-lint
### Check the style and content of the `./Dockerfile*` files
test-docker-lint: ./.env.~out~ ./var/log/docker-login-DOCKER.log
	docker compose pull --quiet hadolint
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) hadolint
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) hadolint \
	    hadolint "./build-host/Dockerfile"

.PHONY: test-push
### Perform any checks that should only be run before pushing.
test-push: $(VCS_FETCH_TARGETS) \
		$(HOME)/.local/var/log/$(PROJECT_NAME)-host-install.log \
		./var-docker/log/build-devel.log ./.env.~out~
	vcs_compare_rev="$(VCS_COMPARE_REMOTE)/$(VCS_COMPARE_BRANCH)"
	if ! git fetch "$(VCS_COMPARE_REMOTE)" "$(VCS_COMPARE_BRANCH)"
	then
# Compare with the pre-release branch if this branch hasn't been pushed yet:
	    vcs_compare_rev="$(VCS_COMPARE_REMOTE)/develop"
	fi
	exit_code=0
	(
	    $(TOX_EXEC_BUILD_ARGS) -- \
	        cz check --rev-range "$${vcs_compare_rev}..HEAD" &&
	    $(TOX_EXEC_BUILD_ARGS) -- \
	        python ./bin/cz-check-bump --compare-ref "$${vcs_compare_rev}"
	) || exit_code=$$?
	if (( $$exit_code == 3 || $$exit_code == 21 ))
	then
	    exit
	elif (( $$exit_code != 0 ))
	then
	    exit $$exit_code
	else
	    docker compose run $(DOCKER_COMPOSE_RUN_ARGS) \
	        $(PROJECT_NAME)-devel $(TOX_EXEC_BUILD_ARGS) -- \
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
### Publish installable packages and container images as required by commits.
release: release-pkgs release-docker

.PHONY: release-pkgs
### Publish installable packages if conventional commits require a release.
release-pkgs: $(HOME)/.local/var/log/$(PROJECT_NAME)-host-install.log
# Only release from the `main` or `develop` branches:
ifeq ($(RELEASE_PUBLISH),true)
	$(MAKE) -e build-pkgs
	true "TEMPLATE: Always specific to the type of project"
	$(MAKE) -e test-clean
endif

.PHONY: release-docker
### Publish all container images to all container registries.
release-docker: build-docker $(DOCKER_REGISTRIES:%=./var/log/docker-login-%.log) \
		$(HOME)/.local/var/log/docker-multi-platform-host-install.log
# Build other platforms in emulation and rely on the layer cache for bundling the
# previously built native images into the manifests.
	DOCKER_BUILD_ARGS="$(DOCKER_BUILD_ARGS) --push"
ifneq ($(DOCKER_PLATFORMS),)
	DOCKER_BUILD_ARGS+=" --platform $(subst $(EMPTY) ,$(COMMA),$(DOCKER_PLATFORMS))"
else
endif
	export DOCKER_BUILD_ARGS
# Push the end-user manifest and images:
	$(MAKE) -e build-docker-build
# Push the development manifest and images:
	$(MAKE) -e DOCKER_VARIANT="devel" build-docker-build
# Update Docker Hub `README.md` using the `./README.rst` reStructuredText version:
ifeq ($(VCS_BRANCH),main)
	$(MAKE) -e "./var/log/docker-login-DOCKER.log"
	docker compose pull --quiet pandoc docker-pushrm
	docker compose up docker-pushrm
endif

.PHONY: release-bump
### Bump the package version if on a branch that should trigger a release.
release-bump: ~/.gitconfig $(VCS_RELEASE_FETCH_TARGETS) \
		./var/log/git-remotes.log \
		$(HOME)/.local/var/log/$(PROJECT_NAME)-host-install.log \
		./var-docker/log/build-devel.log ./.env.~out~
	if ! git diff --cached --exit-code
	then
	    set +x
	    echo "CRITICAL: Cannot bump version with staged changes"
	    false
	fi
# Ensure the local branch is updated to the forthcoming version bump commit:
	git switch -C "$(VCS_BRANCH)" "$$(git rev-parse HEAD)"
# Check if a release is required:
	exit_code=0
	if [ "$(VCS_BRANCH)" = "main" ] &&
	    $(TOX_EXEC_BUILD_ARGS) -- python ./bin/get-base-version $$(
	        $(TOX_EXEC_BUILD_ARGS) -qq -- cz version --project
	    )
	then
# Release a previous pre-release as final regardless of whether commits since then
# require a release:
	    true
	else
# Is a release required by conventional commits:
	    $(TOX_EXEC_BUILD_ARGS) -- python ./bin/cz-check-bump || exit_code=$$?
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
# Build and stage the release notes to be commited by `$ cz bump`
	next_version=$$(
	    $(TOX_EXEC_BUILD_ARGS) -qq -- cz bump $${cz_bump_args} --yes --dry-run |
	    sed -nE 's|.* ([^ ]+) *→ *([^ ]+).*|\2|p;q'
	) || true
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) $(PROJECT_NAME)-devel \
	    $(TOX_EXEC_ARGS) -qq -- \
	    towncrier build --version "$${next_version}" --draft --yes \
	    >"./NEWS-VERSION.rst"
	git add -- "./NEWS-VERSION.rst"
	docker compose run $(DOCKER_COMPOSE_RUN_ARGS) $(PROJECT_NAME)-devel \
	    $(TOX_EXEC_ARGS) -- towncrier build --version "$${next_version}" --yes
# Increment the version in VCS
	$(TOX_EXEC_BUILD_ARGS) -- cz bump $${cz_bump_args}
ifeq ($(VCS_BRANCH),main)
# Merge the bumped version back into `develop`:
	$(MAKE) VCS_BRANCH="main" VCS_MERGE_BRANCH="develop" \
	    VCS_REMOTE="$(VCS_COMPARE_REMOTE)" VCS_MERGE_BRANCH="develop" devel-merge
	git switch -C "$(VCS_BRANCH)" "$$(git rev-parse HEAD)"
endif


## Development Targets:
#
# Recipes used by developers to make changes to the code.

.PHONY: devel-format
### Automatically correct code in this checkout according to linters and style checkers.
devel-format: $(HOME)/.local/var/log/$(PROJECT_NAME)-host-install.log
	true "TEMPLATE: Always specific to the type of project"
	$(TOX_EXEC_BUILD_ARGS) -- reuse addheader -r --skip-unrecognised \
	    --copyright "Ross Patterson <me@rpatterson.net>" --license "MIT" "./"

.PHONY: devel-upgrade
### Update all fixed/pinned dependencies to their latest available versions.
devel-upgrade:
# Update VCS hooks from remotes to the latest tag.
	$(TOX_EXEC_BUILD_ARGS) -- pre-commit autoupdate

.PHONY: devel-upgrade-branch
### Reset an upgrade branch, commit upgraded dependencies on it, and push for review.
devel-upgrade-branch: ~/.gitconfig ./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_BRANCH)
	git switch -C "$(VCS_BRANCH)-upgrade"
	now=$$(date -u)
	$(MAKE) -e devel-upgrade
	if $(MAKE) -e "test-clean"
	then
# No changes from upgrade, exit successfully but push nothing
	    exit
	fi
# Commit the upgrade changes
	echo "Upgrade all requirements to the latest versions as of $${now}." \
	    >"./newsfragments/+upgrade-requirements.bugfix.rst"
	git add --update "./.pre-commit-config.yaml"
	git add "./newsfragments/+upgrade-requirements.bugfix.rst"
	git commit --all --gpg-sign -m \
	    "fix(deps): Upgrade requirements latest versions"
# Fail if upgrading left untracked files in VCS
	$(MAKE) -e "test-clean"

.PHONY: devel-merge
### Merge this branch with a suffix back into it's un-suffixed upstream.
devel-merge: ~/.gitconfig ./var/git/refs/remotes/$(VCS_REMOTE)/$(VCS_MERGE_BRANCH)
	merge_rev="$$(git rev-parse HEAD)"
	git switch -C "$(VCS_MERGE_BRANCH)" --track "$(VCS_REMOTE)/$(VCS_MERGE_BRANCH)"
	git merge --ff --gpg-sign -m \
	    $$'Merge branch \'$(VCS_BRANCH)\' into $(VCS_MERGE_BRANCH)\n\n[ci merge]' \
	    "$${merge_rev}"


## Clean Targets:
#
# Recipes used to restore the checkout to initial conditions.

.PHONY: clean
### Restore the checkout to a state as close to an initial clone as possible.
clean:
	docker compose down --remove-orphans --rmi "all" -v || true
	$(TOX_EXEC_BUILD_ARGS) -- pre-commit uninstall \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push" \
	    || true
	$(TOX_EXEC_BUILD_ARGS) -- pre-commit clean || true
	git clean -dfx -e "/var" -e "var-docker/" -e "/.env" -e "*~"
	rm -rfv "./var/log/" "./var-docker/log/"


## Real Targets:
#
# Recipes that make actual changes and create and update files for the target.

## Docker real targets:

# Build the development image:
./var-docker/log/build-devel.log: ./Dockerfile ./.dockerignore ./bin/entrypoint \
		./build-host/requirements.txt.in ./var-docker/log/rebuild.log \
		./docker-compose.yml ./docker-compose.override.yml ./.env.~out~ \
		./bin/host-install
	true DEBUG Updated prereqs: $(?)
	mkdir -pv "$(dir $(@))"
ifeq ($(DOCKER_BUILD_PULL),true)
# Pull the development image and simulate as if it had been built here.
	if docker compose pull --quiet $(PROJECT_NAME)-devel
	then
	    touch "$(@)" "./var-docker/log/rebuild.log"
	    exit
	fi
endif
	$(MAKE) -e DOCKER_VARIANT="devel" DOCKER_BUILD_ARGS="--load" \
	    build-docker-build | tee -a "$(@)"
# Represent that host install is baked into the image in the `${HOME}` bind volume:
	docker compose run --rm -T --workdir "/home/$(PROJECT_NAME)/" \
	    $(PROJECT_NAME)-devel mkdir -pv "./.local/var/log/"
	docker run --rm --workdir "/home/$(PROJECT_NAME)/" --entrypoint "cat" \
	    "$$(docker compose config --images $(PROJECT_NAME)-devel | head -n 1)" \
	    "./.local/var/log/$(PROJECT_NAME)-host-install.log" |
	    docker compose run --rm -T --workdir "/home/$(PROJECT_NAME)/" \
	        $(PROJECT_NAME)-devel tee -a \
	        "./.local/var/log/$(PROJECT_NAME)-host-install.log" >"/dev/null"

# Build the end-user image:
./var-docker/log/build-user.log: ./var-docker/log/build-devel.log ./Dockerfile \
		./.dockerignore ./bin/entrypoint ./build-host/requirements.txt.in \
		./var-docker/log/rebuild.log
	true DEBUG Updated prereqs: $(?)
# Build the end-user image now that all required artifacts are built"
	mkdir -pv "$(dir $(@))"
	$(MAKE) -e DOCKER_BUILD_ARGS="$(DOCKER_BUILD_ARGS) --load" \
	    build-docker-build >>"$(@)"
# The image installs the host requirements, reflect that in the bind mount volumes
	date >>"$(@:%/build-user.log=%/host-install.log)"

# Marker file used to trigger the rebuild of the image.
# Useful to workaround async timestamp issues when running jobs in parallel:
./var-docker/log/rebuild.log:
	mkdir -pv "$(dir $(@))"
	date >>"$(@)"

# Local environment variables and secrets from a template:
./.env.~out~: ./.env.in
	$(call expand_template,$(<),$(@))

# Install all tools required by recipes that have to be installed externally on the
# host.  Use a target file outside this checkout to support multiple checkouts.  Use a
# target specific to this project so that other projects can use the same approach but
# with different requirements.
$(HOME)/.local/var/log/$(PROJECT_NAME)-host-install.log: ./bin/host-install \
		./build-host/requirements.txt.in
	mkdir -pv "$(dir $(@))"
	"$(<)" |& tee -a "$(@)"

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
	    (
	        docker buildx create --use "multi-platform" || true
	    ) |& tee -a "$(@)"
	fi

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
	$(MAKE) -e "$(HOME)/.local/var/log/$(PROJECT_NAME)-host-install.log"
	$(TOX_EXEC_BUILD_ARGS) -- pre-commit install \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push"

# Tell Emacs where to find checkout-local tools needed to check the code.
./.dir-locals.el.~out~: ./.dir-locals.el.in
	$(call expand_template,$(<),$(@))

# Ensure minimal VCS configuration, mostly useful in automation such as CI.
~/.gitconfig:
	git config --global user.name "$(USER_FULL_NAME)"
	git config --global user.email "$(USER_EMAIL)"

./var/log/docker-login-DOCKER.log:
	$(MAKE) "./.env.~out~"
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


## Makefile "functions":
#
# Snippets whose output is frequently used including across recipes:
# https://www.gnu.org/software/make/manual/html_node/Call-Function.html

# Return the most recently built package:
current_pkg=$(shell ls -t ./dist/*$(1) | head -n 1)

# Have to use a placeholder `*.~out~` as the target instead of the real expanded
# template because we can't disable `.DELETE_ON_ERROR` on a per-target basis.
#
# Short-circuit/repeat the host-install recipe here because expanded templates should
# *not* be updated when `./bin/host-install` is, so we can't use it as a prerequisite,
# *but* it is required to expand templates.  We can't use a sub-make because any
# expanded templates we use in `include ...` directives, such as `./.env`, are updated
# as targets when reading the `./Makefile` leading to endless recursion.
define expand_template=
if ! which envsubst
then
    mkdir -pv "$(HOME)/.local/var/log/"
    ./bin/host-install >"$(HOME)/.local/var/log/$(PROJECT_NAME)-host-install.log"
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
echo "WARNING:Template $(1) has been updated."
echo "        Reconcile changes and \`$$ touch $(2:%.~out~=%)\`."
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
#    ./build/foo.txt: ./foo.txt.in
#    	envsubst <"$(<)" >"$(@)"
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
#         echo "Do some work here" | tee -a "$(@)"
#
# This is also useful when none of the modification times of produced artifacts can be
# counted on to correctly reflect when any subsequent targets need to be updated when
# using this target as a pre-requisite in turn.  If no output can be captured, then the
# recipe can create arbitrary output:
#
#     ./var/log/foo.log:
#         echo "Do some work here"
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


## Maintainer targets:
#
# Recipes not used during the normal course of development.

# TEMPLATE: Run this once for your project.  See the `./var/log/docker-login*.log`
# targets for the authentication environment variables that need to be set or just login
# to those container registries manually and touch these targets.
.PHONY: bootstrap-project
### Run any tasks needed to be run once for a given project by a maintainer
bootstrap-project: ./var/log/docker-login-DOCKER.log
# Initially seed the build host Docker image to bootstrap CI/CD environments
	$(MAKE) -e -C "./build-host/" release
