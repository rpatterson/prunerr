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

# Variables/options that affect behavior
# https://devguide.python.org/versions/#supported-versions
PYTHON_VERSION=3.11

# Values derived from constants
PYTHON_ENV=py$(subst .,,$(PYTHON_VERSION))

# Values derived from the environment
USER_NAME:=$(shell id -u -n)
USER_FULL_NAME=$(shell getent passwd "$(USER_NAME)" | cut -d ":" -f 5 | cut -d "," -f 1)
ifeq ($(USER_FULL_NAME),)
USER_FULL_NAME=$(USER_NAME)
endif
USER_EMAIL=$(USER_NAME)@$(shell hostname --fqdn)
PUID:=$(shell id -u)
PGID:=$(shell id -g)

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

# Strive for as much consistency as possible in development tasks between the local host
# and inside containers.  To that end, most of the `*-docker` container target recipes
# should run the corresponding `*-local` local host target recipes inside the
# development container.  Top level targets, like `test`, should run as much as possible
# inside the development container.

.PHONY: build
### Set up everything for development from a checkout, local and in containers
build: ./.git/hooks/pre-commit build-local build-docker
.PHONY: build-local
### Set up for development locally, directly on the host
build-local: ./var/log/recreate.log
.PHONY: build-docker
### Set up for development in Docker containers
build-docker: ./var/log/docker-build.log
.PHONY: build-bump
### Bump the package version if on a branch that should trigger a release
build-bump: ~/.gitconfig ./var/log/recreate-build.log ./var/log/docker-build.log
# Collect the versions involved in this release according to conventional commits
	cz_bump_args="--check-consistency --no-verify"
ifneq ($(VCS_BRANCH),master)
	cz_bump_args+=" --prerelease beta"
endif
# Run first in case any input is needed from the developer
	exit_code=0
	./.tox/build/bin/cz bump $${cz_bump_args} --dry-run || exit_code=$$?
	rm -fv "./var/cz-bump-no-release.txt"
	if (( $$exit_code == 3 || $$exit_code == 21 ))
	then
# No release necessary for the commits since the last release, don't publish a release
	    echo "true" >"./var/cz-bump-no-release.txt"
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
	docker compose run --rm python-project-structure-devel \
	    towncrier check --compare-with "origin/$(TOWNCRIER_COMPARE_BRANCH)"
	if ! git diff --cached --exit-code
	then
	    set +x
	    echo "CRITICAL: Cannot bump version with staged changes"
	    false
	fi
# Build and stage the release notes to be commited by `$ cz bump`
	docker compose run --rm python-project-structure-devel \
	    towncrier build --version "$${next_version}" --yes
# Increment the version in VCS
	./.tox/build/bin/cz bump $${cz_bump_args}
# Ensure the container image reflects the version bump but we don't need to update the
# requirements again.
	touch "./requirements.txt"
	$(MAKE) "./var/log/docker-build.log"

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
release: release-python release-docker
.PHONY: release-python
### Publish installable Python packages to PyPI
release-python: ./var/log/docker-build.log ./var/log/recreate-build.log ~/.pypirc
# Build Python packages/distributions from the development Docker container for
# consistency/reproducibility.
	docker compose run --rm python-project-structure-devel pyproject-build -w
# https://twine.readthedocs.io/en/latest/#using-twine
	./.tox/build/bin/twine check ./dist/* ./.tox-docker/.pkg/dist/*
	if [ ! -z "$$(git status --porcelain)" ]
	then
	    set +x
	    echo "CRITICAL: Checkout is not clean, not publishing release"
	    false
	fi
	if [ -e "./var/cz-bump-no-release.txt" ]
	then
	    exit
	fi
ifeq ($(RELEASE_PUBLISH),true)
# Publish from the local host outside a container for access to user credentials:
# https://twine.readthedocs.io/en/latest/#using-twine
# Only release on `master` or `develop` to avoid duplicate uploads
	./.tox/build/bin/twine upload -s -r "$(PYPI_REPO)" \
	    ./dist/* ./.tox-docker/.pkg/dist/*
# The VCS remote shouldn't reflect the release until the release has been successfully
# published
	git push --no-verify --tags origin $(VCS_BRANCH)
endif
.PHONY: release-docker
### Publish container images to Docker Hub
release-docker: ./var/log/docker-login.log build-docker
# https://docs.docker.com/docker-hub/#step-5-build-and-push-a-container-image-to-docker-hub-from-your-computer
	docker push "merpatterson/python-project-structure:$(VCS_BRANCH)"
	docker push "merpatterson/python-project-structure:devel-$(VCS_BRANCH)"
	docker push "merpatterson/python-project-structure:$(PYTHON_ENV)-$(VCS_BRANCH)"
	docker push "merpatterson/python-project-structure:$(PYTHON_ENV)-devel-$(VCS_BRANCH)"
ifeq ($(VCS_BRANCH),master)
# Only update tags end users may depend on to be stable from the `master` branch
	current_version=$$(./.tox/build/bin/cz version --project)
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
	docker compose run --rm docker-pushrm
endif

.PHONY: format
### Automatically correct code in this checkout according to linters and style checkers
format: build-local
	./.tox/py3/bin/autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables "./src/pythonprojectstructure/"
	./.tox/py3/bin/autopep8 -v -i -r "./src/pythonprojectstructure/"
	./.tox/py3/bin/black "./src/pythonprojectstructure/"

.PHONY: test
### Format the code and run the full suite of tests, coverage checks, and linters
test: build-docker
# Run from the development Docker container for consistency
	docker compose run --rm python-project-structure-devel make format test-local
.PHONY: test-local
### Run the full suite of tests on the local host
test-local: build-local
	tox
.PHONY: test-docker
### Run the full suite of tests inside a docker container
test-docker: build-docker
	docker compose run --rm python-project-structure-devel make test-local
# Ensure the dist/package has been correctly installed in the image
	docker compose run --rm python-project-structure \
	    python -c 'import pythonprojectstructure; print(pythonprojectstructure)'
.PHONY: test-debug
### Run tests in the main/default environment and invoke the debugger on errors/failures
test-debug: ./var/log/editable.log
	./.tox/py3/bin/pytest --pdb

.PHONY: upgrade
### Update all fixed/pinned dependencies to their latest available versions
upgrade:
	touch "./setup.cfg"
	$(MAKE) PUID=$(PUID) "test"
# Update VCS hooks from remotes to the latest tag.
	./.tox/build/bin/pre-commit autoupdate

.PHONY: clean
### Restore the checkout to a state as close to an initial clone as possible
clean:
	docker compose --remove-orphans down --rmi "all" -v || true
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

./requirements.txt: ./pyproject.toml ./setup.cfg ./tox.ini ./requirements-build.txt.in
	$(MAKE) "./var/log/recreate-build.log"
	tox -e "build"

./var/log/recreate.log: \
		./var/log/host-install.log \
		./requirements.txt ./requirements-devel.txt ./tox.ini
	mkdir -pv "$(dir $(@))"
# Prevent uploading unintended distributions
	rm -vf ./dist/* ./.tox/.pkg/dist/* | tee -a "$(@)"
	tox -r --notest -v | tee -a "$(@)"
# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`
./var/log/editable.log: ./var/log/recreate.log
	./.tox/py3/bin/pip install -e "./" | tee -a "$(@)"
./var/log/recreate-build.log: \
		./var/log/host-install.log ./requirements-build.txt ./tox.ini
	mkdir -pv "$(dir $(@))"
	tox -r -e "build" --notest -v | tee -a "$(@)"

# Docker targets
./var/log/docker-build.log: \
		./Dockerfile ./Dockerfile.devel ./.dockerignore \
		./requirements.txt ./requirements-devel.txt ./bin/entrypoint \
		./docker-compose.yml ./docker-compose.override.yml ./.env \
		./var/log/recreate-build.log
# Ensure access permissions to build artifacts in container volumes.
# If created by `# dockerd`, they end up owned by `root`.
	mkdir -pv "$(dir $(@))" "./var-docker/log/" "./.tox/" "./.tox-docker/" \
	    "./src/python_project_structure.egg-info/" \
	    "./src/python_project_structure-docker.egg-info/"
# Workaround issues with local images and the development image depending on the end
# user image.  It seems that `depends_on` isn't sufficient.
	current_version=$$(./.tox/build/bin/cz version --project)
# https://github.com/moby/moby/issues/39003#issuecomment-879441675
	docker_build_args=" \
	    --build-arg BUILDKIT_INLINE_CACHE=1 \
	    --build-arg PYTHON_VERSION=$(PYTHON_VERSION) \
	    --build-arg VERSION=$${current_version}"
	docker_build_user_tags=" \
	    --tag merpatterson/python-project-structure:local \
	    --tag merpatterson/python-project-structure:$(VCS_BRANCH) \
	    --tag merpatterson/python-project-structure:$${current_version} \
	    --tag merpatterson/python-project-structure:$(PYTHON_ENV)-local \
	    --tag merpatterson/python-project-structure:$(PYTHON_ENV)-$(VCS_BRANCH) \
	    --tag merpatterson/python-project-structure:$(PYTHON_ENV)-$${current_version}"
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
	    --tag merpatterson/python-project-structure:$(PYTHON_ENV)"
endif
	docker buildx build --pull $${docker_build_args} $${docker_build_user_tags} \
	    "./" | tee -a "$(@)"
	docker buildx build $${docker_build_args} \
	    --tag "merpatterson/python-project-structure:devel" \
	    --tag "merpatterson/python-project-structure:devel-$(VCS_BRANCH)" \
	    --tag "merpatterson/python-project-structure:$(PYTHON_ENV)-devel" \
	    --tag "merpatterson/python-project-structure:$(PYTHON_ENV)-devel-$(VCS_BRANCH)"
	    --file "./Dockerfile.devel" "./" | tee -a "$(@)"

# Local environment variables from a template
./.env: ./.env.in
	$(MAKE) "PUID=$(PUID)" "PGID=$(PGID)" \
	    "template=$(<)" "target=$(@)" expand-template

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
	    which tox || pip install tox
	) | tee -a "$(@)"

./.git/hooks/pre-commit: ./var/log/recreate.log
	./.tox/build/bin/pre-commit install \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push"

# Capture any project initialization tasks for reference.  Not actually usable.
 ./pyproject.toml:
	./.tox/build/bin/cz init

# Emacs editor settings
./.dir-locals.el: ./.dir-locals.el.in
	$(MAKE) "template=$(<)" "target=$(@)" expand-template

# User-created pre-requisites
~/.gitconfig:
	git config --global user.name "$(USER_FULL_NAME)"
	git config --global user.email "$(USER_EMAIL)"
~/.pypirc: ./home/.pypirc.in
	$(MAKE) "template=$(<)" "target=$(@)" expand-template
./var/log/docker-login.log: .SHELLFLAGS = -eu -o pipefail -c
./var/log/docker-login.log:
	printenv "DOCKER_PASS" | docker login -u "merpatterson" --password-stdin
	date | tee -a "$(@)"
