## Development, build and maintenance tasks

VENVS = $(shell tox -l)


## Top-level targets

.PHONY: all
all: upgrade

.PHONY: format
format: all
	.tox/lint/bin/autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables ./
	.tox/lint/bin/autopep8 -v -i -r ./
	.tox/lint/bin/black ./

.PHONY: test
test: all format
	tox

.PHONY: upgrade
upgrade: .git/hooks/pre-commit var/log/tox-recreate.log
	make -j $(words $(VENVS:%=upgrade-%)) $(VENVS:%=upgrade-%)


## Real targets

var/log:
	mkdir -p "$(@)"

var/log/tox-recreate.log: var/log setup.py setup.cfg tox.ini
	tox -r --notest -v | tee "$(@)"

.git/hooks/pre-commit: var/log/tox-recreate.log
	.tox/lint/bin/pre-commit install

.PHONY: $(VENVS:%=upgrade-%)
$(VENVS:%=upgrade-%):
	.tox/$(@:upgrade-%=%)/bin/pip install -U --upgrade-strategy=eager .[dev] | \
		tee .tox/$(@:upgrade-%=%)/log/pip-upgrade.log
