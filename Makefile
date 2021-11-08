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

# Variables used to define targets
# Support reuse both locally and in Servarr containers
PREFIX=.

# Options affecting target behavior
PRUNERR_CMD=exec

## Top level targets

.PHONY: all
all: $(PREFIX).venv/bin/prunerr

.PHONY: debug
## Capture how to run Prunerr in the Python interactive debugger
debug: $(PREFIX).venv/bin/prunerr
	"$(<:%/prunerr=/python)" -m "pdb" "$(<)" "$(PRUNERR_CMD)"

.PHONY: clean
clean:
	test -e "$(PREFIX).venv/" && rm -r "$(PREFIX).venv/"

## Real targets

$(PREFIX).venv/bin/prunerr: ./setup.py $(PREFIX).venv/bin/activate
	"$(@:%/prunerr=%/pip)" install wheel
	"$(@:%/prunerr=%/pip)" install -e ".[transmission]"

$(PREFIX).venv/bin/activate:
	python3 -m venv "$(@:%/bin/activate=%/)"
