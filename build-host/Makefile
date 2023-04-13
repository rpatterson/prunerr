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

DOCKER_IMAGE=merpatterson/python-project-structure

## Top-level targets

.PHONY: all
### Default target
all: build

.PHONY: build
### Build the Docker container image
build: ./Dockerfile
	docker pull "$(DOCKER_IMAGE):build-host" || true
	docker buildx build --pull \
	    --build-arg "BUILDKIT_INLINE_CACHE=1" \
	    --cache-from "$(DOCKER_IMAGE):build-host" \
	    --tag "$(DOCKER_IMAGE):build-host" \
	    "./"

.PHONY: release
### Publish the image to this specific CI/CD platform for future caching
release: build
	docker push "$(DOCKER_IMAGE):build-host"


## Debug targets

.PHONY: debug-github-checkout
## Reproduce the GitHub Actions shallow git checkout
debug-github-checkout:
	git init "$(CHECKOUT_DIR)"
	cd "$(CHECKOUT_DIR)"
	git remote add origin \
	    "https://github.com/$(GITHUB_REPOSITORY_OWNER)/python-project-structure"
	rev_hash="$$(git ls-remote -q "origin" "$(VCS_BRANCH)" | cut -f 1)"
	git -c protocol.version=2 fetch --no-tags --prune --progress \
	    --no-recurse-submodules --depth=1 "origin" "$${rev_hash}"
	git checkout --progress --detach "$${rev_hash}"
