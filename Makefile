## Development, build and maintenance tasks

VENVS = $(shell tox -l)


## Top-level targets

.PHONY: all
### Default target
all: build

.PHONY: build
### Perform any currently necessary local set-up common to most operations
build: var/log/init-setup.log .tox/log/recreate.log
.PHONY: build-dist
### Build installable Python packages, mostly to check build locally
build-dist: build
	.tox/build/bin/python -m build

.PHONY: format
### Automatically correct code in this checkout according to linters and style checkers
format: build
	.tox/lint/bin/autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables ./
	.tox/lint/bin/autopep8 -v -i -r --exclude "var" ./
	.tox/lint/bin/black ./

.PHONY: test
### Run the full suite of tests, coverage checks, and linters
test: build format
	tox

.PHONY: test-debug
### Run tests in the main/default environment and invoke the debugger on errors/failures
test-debug: .tox/log/editable.log
	./.tox/py3/bin/pytest --pdb

.PHONY: upgrade
### Update all fixed/pinned dependencies to their latest available versions
upgrade:
	touch "./pyproject.toml"
	$(MAKE) "test"

.PHONY: clean
### Restore the checkout to a state as close to an initial clone as possible
clean:
	git clean -dfx -e "var/"


## Real targets

requirements.txt: pyproject.toml setup.cfg tox.ini
	tox -r -e "build"

.tox/log/recreate.log: requirements.txt tox.ini
	mkdir -pv "$(dir $(@))"
	tox -r --notest -v | tee "$(@)"
# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`
.tox/log/editable.log: .tox/log/recreate.log
	./.tox/py3/bin/pip install -e "./"

# Perform any one-time local checkout set up
var/log/init-setup.log: .git/hooks/pre-commit .git/hooks/pre-push
	mkdir -pv "$(dir $(@))"
	date >> "$(@)"

.git/hooks/pre-commit: .tox/log/recreate.log
	.tox/lint/bin/pre-commit install

.git/hooks/pre-push: .tox/log/recreate.log
	.tox/lint/bin/pre-commit install --hook-type pre-push
