## Development, build and maintenance tasks


## Top-level targets

.PHONY: all
all: .tox ../.git/hooks/pre-commit

.PHONY: test
test: all
	tox


## Real targets

.tox: setup.py setup.cfg
	tox -r --notest -v
	touch "$(@)"

../.git/hooks/pre-commit: .tox
	.tox/py3/bin/pre-commit install
