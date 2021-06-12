### Prunerr development set-up and tasks

### Defensive settings for make:
#     https://tech.davis-hansson.com/p/make/
SHELL := bash
.ONESHELL:
.SHELLFLAGS := -xeu -o pipefail -c
.SILENT:
.DELETE_ON_ERROR:
MAKEFLAGS += --warn-undefined-variables
MAKEFLAGS += --no-builtin-rules


## Top level targets

.PHONY: all
all: ./.venv/bin/prunerr

.PHONY: clean
clean:
	test -e "./.venv/" && rm -r "./.venv/"

## Real targets

./.venv/bin/prunerr: ./setup.py ./.venv/bin/activate
	"$(@:%/prunerr=%/pip)" install -e "."

./.venv/bin/activate:
	python3 -m venv "$(@:%/bin/activate=%/)"
