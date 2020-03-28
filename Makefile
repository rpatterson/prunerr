## Development, build and maintenance tasks


## Top-level targets

.PHONY: all
all: .tox ../.git/hooks/pre-commit

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


## Real targets

.tox: setup.py setup.cfg tox.ini
	tox -r --notest -v
	touch "$(@)"

../.git/hooks/pre-commit: .tox
	.tox/lint/bin/pre-commit install
