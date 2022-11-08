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

# Derived values
VENVS = $(shell tox -l)


## Top-level targets

.PHONY: all
### Default target
all: build

.PHONY: build
### Perform any currently necessary local set-up common to most operations
build: ./var/log/init-setup.log ./var/log/recreate.log
.PHONY: build-dist
### Build installable Python packages, mostly to check build locally
build-dist: build
	./.tox/build/bin/python -m build

.PHONY: format
### Automatically correct code in this checkout according to linters and style checkers
format: build
	./.tox/lint/bin/autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables ./
	./.tox/lint/bin/autopep8 -v -i -r --exclude "var" ./
	./.tox/lint/bin/black ./

.PHONY: test
### Run the full suite of tests, coverage checks, and linters
test: build format
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

.PHONY: clean
### Restore the checkout to a state as close to an initial clone as possible
clean:
	test ! -x "./.tox/lint/bin/pre-commit" || (
	    ./.tox/lint/bin/pre-commit uninstall --hook-type pre-push
	    ./.tox/lint/bin/pre-commit uninstall
	    ./.tox/lint/bin/pre-commit clean
	)
	git clean -dfx -e "var/"
	rm -vf "./var/log/init-setup.log" "./var/log/recreate.log" \
	    "./var/log/editable.log"


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
	tox -r --notest -v | tee "$(@)"
# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`
./var/log/editable.log: ./var/log/recreate.log
	./.tox/py3/bin/pip install -e "./"

# Perform any one-time local checkout set up
./var/log/init-setup.log: ./.git/hooks/pre-commit ./.git/hooks/pre-push
	mkdir -pv "$(dir $(@))"
	date >> "$(@)"

./.git/hooks/pre-commit: ./var/log/recreate.log
	./.tox/lint/bin/pre-commit install

./.git/hooks/pre-push: ./var/log/recreate.log
	./.tox/lint/bin/pre-commit install --hook-type pre-push


# Emacs editor settings
./.dir-locals.el: ./.dir-locals.el.in
	$(MAKE) "template=$(<)" "target=$(@)" expand-template
