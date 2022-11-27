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

# Options controlling behavior
VCS_BRANCH:=$(shell git branch --show-current)


## Top-level targets

.PHONY: all
### Default target
all: build

.PHONY: build
### Perform any currently necessary local set-up common to most operations
build: ./var/log/recreate.log ./.git/hooks/pre-commit
.PHONY: build-dist
### Build installable Python packages, mostly to check build locally
build-dist: build
	./.tox/build/bin/python -m build

.PHONY: check-push
### Perform any checks that should only be run before pushing
check-push: build
	./.tox/py3/bin/towncrier check

.PHONY: release
### Publish installable Python packages to PyPI
release: ./var/log/recreate.log ~/.gitconfig ~/.pypirc
# Collect the versions involved in this release according to conventional commits
	current_version=$$(./.tox/py3/bin/semantic-release print-version --current)
	next_version=$$(./.tox/py3/bin/semantic-release print-version --next)
# Update the release notes/changelog
	./.tox/py3/bin/towncrier build --yes
	git commit --no-verify -s -m \
	    "build(release): Update changelog v$${current_version} -> v$${next_version}"
# Increment the version in VCS
	./.tox/py3/bin/semantic-release version
# Prevent uploading unintended distributions
	rm -vf ./dist/*
# Build the actual release artifacts
	$(MAKE) build-dist
# https://twine.readthedocs.io/en/latest/#using-twine
	./.tox/py3/bin/twine check dist/*
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
test: ./var/log/install-tox.log build format
	tox

.PHONY: test-debug
### Run tests in the main/default environment and invoke the debugger on errors/failures
test-debug: ./var/log/editable.log
	./.tox/py3/bin/pytest --pdb

.PHONY: upgrade
### Update all fixed/pinned dependencies to their latest available versions
upgrade:
	touch "./pyproject.toml"
	$(MAKE) "test"
# Update VCS hooks from remotes to the latest tag.
	./.tox/lint/bin/pre-commit autoupdate

.PHONY: clean
### Restore the checkout to a state as close to an initial clone as possible
clean:
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

./requirements.txt: ./var/log/install-tox.log ./pyproject.toml ./setup.cfg ./tox.ini
	tox -e "build"

./var/log/recreate.log: \
		./var/log/install-tox.log \
		./requirements.txt ./requirements-devel.txt ./tox.ini
	mkdir -pv "$(dir $(@))"
	tox -r --notest -v | tee -a "$(@)"
# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`
./var/log/editable.log: ./var/log/recreate.log
	./.tox/py3/bin/pip install -e "./" | tee -a "$(@)"

# Perform any one-time local checkout set up
./var/log/install-tox.log:
	mkdir -pv "$(dir $(@))"
	(which tox || pip install tox) | tee -a "$(@)"

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
~/.gitconfig:
	git config --global user.name "$(USER_FULL_NAME)"
	git config --global user.email "$(USER_EMAIL)"
~/.pypirc: ./home/.pypirc.in
	$(MAKE) "template=$(<)" "target=$(@)" expand-template
