## Development, build and maintenance tasks

### Defensive settings for make:
#     https://tech.davis-hansson.com/p/make/
SHELL:=bash
.ONESHELL:
.SHELLFLAGS:=-xeu -o pipefail -c
.SILENT:
.DELETE_ON_ERROR:
MAKEFLAGS+=--warn-undefined-variables
MAKEFLAGS+=--no-builtin-rules
PS1?=$$

# Options controlling behavior
VCS_BRANCH:=$(shell git branch --show-current)
export PUID:=$(shell id -u)
export PGID:=$(shell id -g)

# Derived values
VENVS = $(shell tox -l)


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
build: ./var/log/init-setup.log build-local build-docker
.PHONY: build-local
### Set up for development locally, directly on the host
build-local: ./var/log/recreate.log
.PHONY: build-docker
### Set up for development in Docker containers
build-docker: ./var/log/docker-build.log
.PHONY: build-dist
### Build installable Python packages, mostly to check build locally
build-dist: build-local
	./.tox/build/bin/python -m build

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
check-push: build
	./.tox/py3/bin/towncrier check

.PHONY: release
### Publish installable Python packages to PyPI and container images to Docker Hub
release: release-python release-docker
.PHONY: release-python
### Publish installable Python packages to PyPI
release-python: ./var/log/recreate.log ~/.pypirc
# Collect the versions involved in this release according to conventional commits
	current_version=$$(./.tox/py3/bin/semantic-release print-version --current)
	next_version=$$(./.tox/py3/bin/semantic-release print-version --next)
# Update the release notes/changelog
	./.tox/py3/bin/towncrier build --yes
	git commit --no-verify -s -m \
	    "build(release): Update changelog v${current_version} -> v${next_version}"
# Increment the version in VCS
	./.tox/py3/bin/semantic-release version
# Prevent uploading unintended distributions
	rm -vf ./dist/*
# Build Python packages/distributions from the development Docker container for
# consistency/reproducibility.
	docker compose run --rm python-project-structure.devel make build-dist
# https://twine.readthedocs.io/en/latest/#using-twine
	./.tox/py3/bin/twine check dist/*
# Publish from the local host outside a container for access to user credentials:
# https://twine.readthedocs.io/en/latest/#using-twine
# Only release on `master` or `develop` to avoid duplicate uploads
ifeq ($(VCS_BRANCH), master)
# Ensure the release commit and tag are on the remote before publishing release
# artifacts
	git push --no-verify --tags origin $(VCS_BRANCH)
	./.tox/py3/bin/twine upload -s -r "pypi" dist/*
else ifeq ($(VCS_BRANCH), develop)
	git push --no-verify --tags origin $(VCS_BRANCH)
# Release to the test PyPI server on the `develop` branch
	./.tox/py3/bin/twine upload -s -r "testpypi" dist/*
endif
.PHONY: release-docker
### Publish container images to Docker Hub
release-docker: ./var/log/docker-login.log build-docker
# https://docs.docker.com/docker-hub/#step-5-build-and-push-a-container-image-to-docker-hub-from-your-computer
ifeq ($(VCS_BRANCH), master)
	docker push "merpatterson/python-project-structure"
	docker compose up docker-pushrm
endif

.PHONY: format
### Automatically correct code in this checkout according to linters and style checkers
format: build-local
	./.tox/lint/bin/autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables ./
	./.tox/lint/bin/autopep8 -v -i -r --exclude "var" ./
	./.tox/lint/bin/black ./

.PHONY: test
### Format the code and run the full suite of tests, coverage checks, and linters
test: build-docker
# Run from the development Docker container for consistency
	docker compose run --rm python-project-structure.devel make format test-local
.PHONY: test-local
### Run the full suite of tests on the local host
test-local: build-local
	tox
.PHONY: test-docker
### Run the full suite of tests inside a docker container
test-docker: build-docker
	docker compose run --rm python-project-structure.devel make test-local
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
	touch "./pyproject.toml"
	$(MAKE) PUID=$(PUID) "test"
# Update VCS hooks from remotes to the latest tag.
	./.tox/lint/bin/pre-commit autoupdate

.PHONY: clean
### Restore the checkout to a state as close to an initial clone as possible
clean:
	docker compose --remove-orphans down --rmi "all" -v || true
	./.tox/lint/bin/pre-commit uninstall \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push" \
	    || true
	./.tox/lint/bin/pre-commit clean || true
	git clean -dfx -e "var/"
	rm -rfv "./var/log/"


## Utility targets

.PHONY: expand-template
## Create a file from a template replacing environment variables
expand-template: .SHELLFLAGS = -eu -o pipefail -c
expand-template:
	if [ -e "$(target)" ]
	then
	    echo "WARNING: Template $(template) has been updated:"
	    echo "Reconcile changes and \`$$ touch $(target)\`:"
	    diff -u "$(target)" "$(template)" || true
	    false
	fi
	envsubst <"$(template)" >"$(target)"


## Real targets

./requirements.txt: ./pyproject.toml ./setup.cfg ./tox.ini
	tox -e "build"

./var/log/recreate.log: ./requirements.txt ./requirements-devel.txt ./tox.ini
	mkdir -pv "$(dir $(@))"
	tox -e "ALL" -r --notest -v | tee -a "$(@)"
# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`
./var/log/editable.log: ./var/log/recreate.log
	./.tox/py3/bin/pip install -e "./" | tee -a "$(@)"

# Docker targets
./var/log/docker-build.log: \
		./Dockerfile ./Dockerfile.devel ./.dockerignore ./bin/entrypoint \
		./docker-compose.yml ./docker-compose.override.yml ./.env
# Ensure access permissions to build artifacts in container volumes.
# If created by `# dockerd`, they end up owned by `root`.
	mkdir -pv "$(dir $(@))" "./var-docker/" "./.tox-docker/" \
	    "./src/python_project_structure-docker.egg-info/"
# Workaround issues with local images and the development image depending on the end
# user image.  It seems that `depends_on` isn't sufficient.
	docker compose build --pull python-project-structure | tee -a "$(@)"
	docker compose build | tee -a "$(@)"
# Prepare the testing environment and tools as much as possible to reduce development
# iteration time when using the image.
	docker compose run --rm python-project-structure.devel make build-local

# Local environment variables from a template
./.env: ./.env.in
	$(MAKE) "template=$(<)" "target=$(@)" expand-template

# Perform any one-time local checkout set up
./var/log/init-setup.log: ./.git/hooks/pre-commit
	mkdir -pv "$(dir $(@))"
	date | tee -a "$(@)"

./.git/hooks/pre-commit: ./var/log/recreate.log
	./.tox/lint/bin/pre-commit install \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push"

# Capture any project initialization tasks for reference.  Not actually usable.
 ./pyproject.toml:
	./.tox/py3/bin/cz init

# Emacs editor settings
./.dir-locals.el: ./.dir-locals.el.in
	$(MAKE) "template=$(<)" "target=$(@)" expand-template

# User-created pre-requisites
~/.pypirc: .SHELLFLAGS = -eu -o pipefail -c
~/.pypirc:
	echo "You must create your ~/.pypirc file:
	    https://packaging.python.org/en/latest/specifications/pypirc/"
	false
./var/log/docker-login.log:
	docker login
	date | tee -a "$(@)"
