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

# Values derived from the environment
USER_NAME:=$(shell id -u -n)
USER_FULL_NAME=$(shell getent passwd "$(USER_NAME)" | cut -d ":" -f 5 | cut -d "," -f 1)
ifeq ($(USER_FULL_NAME),)
USER_FULL_NAME=$(USER_NAME)
endif
USER_EMAIL=$(USER_NAME)@$(shell hostname --fqdn)
PUID:=$(shell id -u)
PGID:=$(shell id -g)

# Options controlling behavior
VCS_BRANCH:=$(shell git branch --show-current)


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
.PHONY: build-dist
### Build installable Python packages, mostly to check build locally
build-dist: build-local
	./.tox/py3/bin/pyproject-build

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
	./.tox/build/bin/towncrier check

.PHONY: release
### Publish installable Python packages to PyPI and container images to Docker Hub
release: release-python release-docker
.PHONY: release-python
### Publish installable Python packages to PyPI
release-python: ./var/log/gpg-import.log ~/.gitconfig ~/.pypirc \
		./var/log/recreate-build.log
ifneq ($(GPG_SIGNING_PRIVATE_KEY),)
# Import the private signing key from CI secrets
	$(MAKE) ./var/log/gpg-import.log
endif
# Collect the versions involved in this release according to conventional commits
	current_version=$$(./.tox/build/bin/semantic-release print-version --current)
	next_version=$$(./.tox/build/bin/semantic-release print-version --next)
# Update the release notes/changelog
	./.tox/build/bin/towncrier build --yes
	git commit --no-verify -s -m \
	    "build(release): Update changelog v$${current_version} -> v$${next_version}"
# Increment the version in VCS
	./.tox/build/bin/semantic-release version
# Prevent uploading unintended distributions
	rm -vf ./dist/*
# Build Python packages/distributions from the development Docker container for
# consistency/reproducibility.
	docker compose run --rm python-project-structure.devel make build-dist
# https://twine.readthedocs.io/en/latest/#using-twine
	./.tox/build/bin/twine check dist/*
# Publish from the local host outside a container for access to user credentials:
# https://twine.readthedocs.io/en/latest/#using-twine
# Only release on `master` or `develop` to avoid duplicate uploads
ifeq ($(VCS_BRANCH), master)
# Ensure the release commit and tag are on the remote before publishing release
# artifacts
	./.tox/build/bin/twine upload -s -r "pypi" dist/*
# The VCS remote shouldn't reflect the release until the release has been successfully
# published
	git push --no-verify --tags origin $(VCS_BRANCH)
else ifeq ($(VCS_BRANCH), develop)
# Release to the test PyPI server on the `develop` branch
	./.tox/build/bin/twine upload -s -r "testpypi" dist/*
	git push --no-verify --tags origin $(VCS_BRANCH)
endif
.PHONY: release-docker
### Publish container images to Docker Hub
release-docker: build-docker
# https://docs.docker.com/docker-hub/#step-5-build-and-push-a-container-image-to-docker-hub-from-your-computer
ifeq ($(VCS_BRANCH), master)
ifneq ($(DOCKER_PASS),)
	$(MAKE) ./var/log/docker-login.log
endif
	docker push "merpatterson/python-project-structure"
	docker compose up docker-pushrm
endif

.PHONY: format
### Automatically correct code in this checkout according to linters and style checkers
format: build-local
	./.tox/py3/bin/autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables ./
	./.tox/py3/bin/autopep8 -v -i -r --exclude "var" ./
	./.tox/py3/bin/black ./

.PHONY: test
### Format the code and run the full suite of tests, coverage checks, and linters
test: build-docker
# Run from the development Docker container for consistency
	docker compose run --rm python-project-structure.devel make format test-local
.PHONY: test-local
### Run the full suite of tests on the local host
test-local: ./var/log/install-tox.log build-local
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

./requirements.txt: \
		./var/log/recreate-build.log ./pyproject.toml ./setup.cfg ./tox.ini \
		./requirements-build.txt.in
	tox -e "build"
# Avoid a tox recreation loop
	touch -r "./requirements-build.txt" "./var/log/recreate-build.log" "$(@)"

./var/log/recreate.log: \
		./var/log/install-tox.log \
		./requirements.txt ./requirements-devel.txt ./tox.ini
	mkdir -pv "$(dir $(@))"
	tox -r --notest -v | tee -a "$(@)"
# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`
./var/log/editable.log: ./var/log/recreate.log
	./.tox/py3/bin/pip install -e "./" | tee -a "$(@)"
./var/log/recreate-build.log: \
		./var/log/install-tox.log ./requirements-build.txt ./tox.ini
	mkdir -pv "$(dir $(@))"
	tox -r -e "build" --notest -v | tee -a "$(@)"

# Docker targets
./var/log/docker-build.log: \
		./Dockerfile ./Dockerfile.devel ./.dockerignore \
		./requirements.txt ./requirements-devel.txt ./bin/entrypoint \
		./docker-compose.yml ./docker-compose.override.yml ./.env
# Ensure access permissions to build artifacts in container volumes.
# If created by `# dockerd`, they end up owned by `root`.
	mkdir -pv "$(dir $(@))" "./var-docker/log/" "./.tox/" "./.tox-docker/" \
	    "./src/python_project_structure.egg-info/" \
	    "./src/python_project_structure-docker.egg-info/"
# Workaround issues with local images and the development image depending on the end
# user image.  It seems that `depends_on` isn't sufficient.
	docker compose build --pull python-project-structure | tee -a "$(@)"
	docker compose build | tee -a "$(@)"
# Prepare the testing environment and tools as much as possible to reduce development
# iteration time when using the image.
	test -e "./var-docker/log/recreate-build.log" ||
	    ln -v "./var/log/recreate-build.log" "./var-docker/log/recreate-build.log"
	docker compose run --rm python-project-structure.devel make build-local

# Local environment variables from a template
./.env: ./.env.in
	$(MAKE) "PUID=$(PUID)" "PGID=$(PGID)" \
	    "template=$(<)" "target=$(@)" expand-template

# Perform any one-time local checkout set up
./var/log/install-tox.log:
	mkdir -pv "$(dir $(@))"
	(which tox || pip install tox) | tee -a "$(@)"

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
GPG_SIGNING_KEYID=
./home/.gnupg/ci-cd-signing-subkey.asc:
# We need a private key in the CI/CD environment for signing release commits and
# artifacts.  Use a subkey so that it can be revoked without affecting your main key.
# If the private signing subkey were protected/encrypted with a passphrase, then we'd
# need both the exported private signing subkey *and* that passphrase in CI/CD secrets.
# To my mind, that defeats the purpose of protecting private keys with passphrases, so I
# prefer to just add exported private signing subkey to CI in unprotected/un-encrypted
# form.  Unfortunately, `$ gpg` makes this very hard to do so other developers using
# this template may prefer to do it the other way and also add a passphrase in CI
# secrets.  This recipe captures what I had to do to export an unprotected/un-encrypted
# private signing subkey.  It's very fragile and not widely tested so it should probably
# only be used for reference.  It worked for me but the risk is leaking your main
# private key so double and triple check all your assumptions and results.
# 1. Create a signing subkey: https://wiki.debian.org/Subkeys#How.3F
# 2. Get the long key ID for that private subkey:
#	gpg --list-secret-keys --keyid-format "LONG"
# 3. Export *just* that private subkey and verify that the main secret key packet is the
#    GPG dummy packet and that the only other private key included is the intended
#    subkey:
#	gpg --armor --export-secret-subkeys "$(GPG_SIGNING_KEYID)!" |
#	    gpg --list-packets
# We need to remove the password from the exported private subkey.  Unfortunately, `$
# gpg` lost the ability to do this non-interactively some time back which makes this
# quite a PITA.
# 4. Import the exported key into a temporary GNU PG directory:
	rm -rfv "$(dir $(@))"
	gpg --armor --export-secret-subkeys "$(GPG_SIGNING_KEYID)!" |
	    gpg --homedir "$(dir $(@))" --import
# 5. Remove the password from the exported private subkey:
#    https://lists.gnupg.org/pipermail/gnupg-users/2017-December/059617.html
	gpg --homedir "$(dir $(@))" --edit-key "$(GPG_SIGNING_KEYID)!" passwd
# 6. Confirm the private subkey is no longer password protected in the temporary GNU PG
#    directory:
	echo "Test signature content" >"$(dir $(@))test-sig.txt"
	gpgconf --kill gpg-agent
	gpg --homedir "$(dir $(@))" --local-user "$(GPG_SIGNING_KEYID)!" \
	    --sign "$(dir $(@))/test-sig.txt"
# 7. At long last we can export *just* the private signing subkey without password
#    protection:
	gpg --homedir "$(dir $(@))" --armor --export-secret-subkeys \
	    "$(GPG_SIGNING_KEYID)!" >"$(@)"
# 8. Add the contents of this target as a `GPG_SIGNING_PRIVATE_KEY` secret in CI
./var/log/gpg-import.log: .SHELLFLAGS = -eu -o pipefail -c
./var/log/gpg-import.log:
# 9. In each CI run, import the private signing key from the CI secrets
	if [ -z "$(GPG_SIGNING_PRIVATE_KEY)" ]
	then
	    echo "The GPG_SIGNING_PRIVATE_KEY env var is required,"
	    echo "or '$$ touch $(@)' to bypass this and test releases locally"
	    false
	fi
	echo -n "$(GPG_SIGNING_PRIVATE_KEY)" | gpg --import | tee -a "$(@)"
~/.pypirc: ./home/.pypirc.in
	$(MAKE) "template=$(<)" "target=$(@)" expand-template
./var/log/docker-login.log: .SHELLFLAGS = -eu -o pipefail -c
./var/log/docker-login.log:
	docker login -u "merpatterson" -p "$(DOCKER_PASS)"
	date | tee -a "$(@)"
