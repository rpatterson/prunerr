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
TWINE_UPLOAD_AGS=-r "testpypi"
export PUID=1000
export PGID=100

# Derived values
VENVS = $(shell tox -l)


## Top-level targets

.PHONY: all
### Default target
all: build

.PHONY: build
### Perform any currently necessary local set-up common to most operations
build: ./var/log/init-setup.log ./var/log/recreate.log ./var/log/docker-build.log
.PHONY: build-dist
### Build installable Python packages, mostly to check build locally
build-dist: build
	./.tox/build/bin/python -m build

.PHONY: start
### Run the local development end-to-end stack services in the background as daemons
start: build
	docker compose down
	docker compose up -d
.PHONY: run
### Run the local development end-to-end stack services in the foreground for debugging
run: build
	docker compose down
	docker compose up

.PHONY: release
### Publish installable Python packages to PyPI and container images to Docker Hub
release: ~/.pypirc ./var/log/docker-login.log test-docker
# Prevent uploading unintended distributions
	rm -v ./dist/*
	$(MAKE) build-dist
# https://twine.readthedocs.io/en/latest/#using-twine
	./.tox/py3/bin/twine check dist/*
	./.tox/py3/bin/twine upload -s $(TWINE_UPLOAD_AGS) dist/*
# https://docs.docker.com/docker-hub/#step-5-build-and-push-a-container-image-to-docker-hub-from-your-computer
	docker push "merpatterson/python-project-structure"
	docker compose up docker-pushrm

.PHONY: format
### Automatically correct code in this checkout according to linters and style checkers
format:
	./.tox/lint/bin/autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables ./
	./.tox/lint/bin/autopep8 -v -i -r --exclude "var" ./
	./.tox/lint/bin/black ./

.PHONY: test
### Run the full suite of tests, coverage checks, and linters
test: build format test-docker
.PHONY: test-docker
### Run the full suite of tests inside a docker container
test-docker: ./var/log/docker-build.log
	id
	ls -an ./.tox*/
	docker compose run --rm --entrypoint="id" python-project-structure.devel
	docker compose run --rm --entrypoint="ls" python-project-structure.devel \
	    -an ./.tox*/
	docker compose run --rm python-project-structure.devel
# Ensure the dist/package has been correctly installed in the image
	docker compose run --rm --entrypoint="python" python-project-structure \
	    -c 'import pythonprojectstructure; print(pythonprojectstructure)'

.PHONY: test-debug
### Run tests in the main/default environment and invoke the debugger on errors/failures
test-debug: ./var/log/editable.log
	./.tox/py3/bin/pytest --pdb

.PHONY: upgrade
### Update all fixed/pinned dependencies to their latest available versions
upgrade:
	touch "./pyproject.toml"
	$(MAKE) PUID=$(PUID) "test"

.PHONY: clean
### Restore the checkout to a state as close to an initial clone as possible
clean:
	docker compose down --rmi "all" -v || true
	./.tox/lint/bin/pre-commit uninstall --hook-type pre-push || true
	./.tox/lint/bin/pre-commit uninstall || true
	./.tox/lint/bin/pre-commit clean || true
	git clean -dfx -e "var/"
	rm -vf "./var/log/init-setup.log" "./var/log/recreate.log" \
	    "./var/log/editable.log" "./var/log/docker-build.log"


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
	tox -r -e "build"

./var/log/recreate.log: ./requirements.txt ./requirements-devel.txt ./tox.ini
	mkdir -pv "$(dir $(@))"
	tox -r --notest -v | tee -a "$(@)"
# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`
./var/log/editable.log: ./var/log/recreate.log
	./.tox/py3/bin/pip install -e "./" | tee -a "$(@)"

# Docker targets
./var/log/docker-build.log: \
		./requirements.txt ./requirements-devel.txt \
		./Dockerfile ./Dockerfile.devel ./.dockerignore \
		./docker-compose.yml ./docker-compose.override.yml \
		./.env
# Ensure access permissions to the `./.tox/` directory inside docker.  If created by `#
# dockerd`, it ends up owned by `root`.
	mkdir -pv "./.tox-docker/" "./src/python_project_structure-docker.egg-info/" |
	    tee -a "$(@)"
# Workaround issues with local images and the development image depending on the end
# user image.  It seems that `depends_on` isn't sufficient.
	docker compose build --pull python-project-structure | tee -a "$(@)"
	docker compose build | tee -a "$(@)"

# Local environment variables from a template
./.env: ./.env.in
	$(MAKE) "template=$(<)" "target=$(@)" expand-template

# Perform any one-time local checkout set up
./var/log/init-setup.log: ./.git/hooks/pre-commit ./.git/hooks/pre-push
	mkdir -pv "$(dir $(@))"
	date | tee -a "$(@)"

./.git/hooks/pre-commit: ./var/log/recreate.log
	./.tox/lint/bin/pre-commit install

./.git/hooks/pre-push: ./var/log/recreate.log
	./.tox/lint/bin/pre-commit install --hook-type pre-push

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
