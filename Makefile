## Development, build and maintenance tasks


## Top-level targets

.PHONY: all
all: .venv ../.git/hooks/pre-commit

.PHONY: test
test: all
	tox


## Real targets

.venv: pyproject.toml poetry.toml poetry.lock
	poetry install

../.git/hooks/pre-commit: .venv
	poetry run pre-commit install
