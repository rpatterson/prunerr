## Build and publish an image in which to build, test, and release the project

### Defensive settings for make:
#     https://tech.davis-hansson.com/p/make/
SHELL:=bash
.ONESHELL:
.SHELLFLAGS:=-eu -o pipefail -c
.SILENT:
.DELETE_ON_ERROR:
MAKEFLAGS+=--warn-undefined-variables
MAKEFLAGS+=--no-builtin-rules
PS1?=$$
EMPTY=
COMMA=,

# Done with `$(shell ...)`, echo recipe commands going forward
.SHELLFLAGS+= -x

CI_REGISTRY_IMAGE=merpatterson/python-project-structure

## Top-level targets

.PHONY: all
### Default target
all: build

.PHONY: build
### Build the Docker container image
build: ./Dockerfile
	docker pull "$(CI_REGISTRY_IMAGE):build-host" || true
	docker buildx build --pull \
	    --build-arg "BUILDKIT_INLINE_CACHE=1" \
	    --cache-from "$(CI_REGISTRY_IMAGE):build-host" \
	    --tag "$(CI_REGISTRY_IMAGE):build-host" \
	    "./"

.PHONY: release
### Publish the image to this specific CI/CD platform for future caching
release: build
	docker push "$(CI_REGISTRY_IMAGE):build-host"
