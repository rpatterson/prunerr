## Development, build and maintenance tasks

VENVS = $(shell tox -l)


## Top-level targets

.PHONY: all
all: build

.PHONY: build
build: var/log/tox-recreate.log

.PHONY: format
format: var/log/tox-recreate.log
	.tox/lint/bin/autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables ./
	.tox/lint/bin/autopep8 -v -i -r --exclude "var" ./
	.tox/lint/bin/black ./

.PHONY: test
test: build format
	tox

.PHONY: test-debug
test-debug: var/log/tox-recreate.log
	./.tox/py3/bin/pytest --pdb

.PHONY: upgrade
upgrade: .git/hooks/pre-commit .git/hooks/pre-push
	touch "./setup.py"
	$(MAKE) "test"


## Real targets

requirements.txt: setup.py setup.cfg tox.ini
	tox -r -e "pip-tools"

var/log/tox-recreate.log: requirements.txt tox.ini
	mkdir -p "var/log"
	tox -r --notest -v | tee "$(@)"

.git/hooks/pre-commit: var/log/tox-recreate.log
	.tox/lint/bin/pre-commit install

.git/hooks/pre-push: var/log/tox-recreate.log
	.tox/lint/bin/pre-commit install --hook-type pre-push
