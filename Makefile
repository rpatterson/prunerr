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
PUID=1000
PGID=100
PRUNERR_CMD=exec


## Top level targets

.PHONY: all
all: build

.PHONY: build
build: $(PREFIX)/.venv/bin/prunerr ./.env
	docker-compose build --pull --build-arg "PUID=$(PUID)" --build-arg "PGID=$(PGID)"

.PHONY: expand-template
## Create a file from a template replacing environment variables
expand-template: .SHELLFLAGS = -eu -o pipefail -c
expand-template:
	if [ -e "$(target)" ]
	then
	    echo "WARNING: Template $(template) has been updated:"
	    diff -u "$(target)" "$(template)" || true
	else
	    envsubst <"$(template)" >"$(target)"
	fi

.PHONY: debug
## Capture how to run Prunerr in the Python interactive debugger
debug: $(PREFIX)/.venv/bin/prunerr
	"$(<:%/prunerr=%/python)" -m "pdb" "$(<)" "$(PRUNERR_CMD)"

.PHONY: clean
clean:
	test -e "$(PREFIX)/.venv/" && rm -r "$(PREFIX)/.venv/"


## Real targets

$(PREFIX)/.venv/bin/prunerr: ./setup.py ./requirements.txt $(PREFIX)/.venv/bin/activate
	"$(@:%/prunerr=%/pip)" install wheel
	"$(@:%/prunerr=%/pip)" install -r "./requirements.txt"
	"$(@:%/prunerr=%/python)" -m "spacy" download "en_core_web_sm"

$(PREFIX)/.venv/bin/activate:
	python3 -m venv "$(@:%/bin/activate=%/)"

./.env: ./.env.in /usr/bin/apg
	export TRANSMISSION_PASS="$(apg -n 1)"
	$(MAKE) "template=$(<)" "target=$(@)" expand-template

/usr/bin/apg:
	apt-get update
	apt-get install -y "$(@:/usr/bin/%=%)"
