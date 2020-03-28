## Development, build and maintenance tasks


## Top-level targets

.PHONY: all
all: .venv


## Real targets

.venv: pyproject.toml poetry.toml poetry.lock
	poetry install
