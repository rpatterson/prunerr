## Development, build and maintenance tasks

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

# Project-specific variables
GPG_SIGNING_KEYID=2EFF7CCE6828E359
GITHUB_REPOSITORY_OWNER=rpatterson
CI_REGISTRY_IMAGE=registry.gitlab.com/$(GITHUB_REPOSITORY_OWNER)/python-project-structure

# Values derived from the environment
USER_NAME:=$(shell id -u -n)
USER_FULL_NAME=$(shell getent passwd "$(USER_NAME)" | cut -d ":" -f 5 | cut -d "," -f 1)
ifeq ($(USER_FULL_NAME),)
USER_FULL_NAME=$(USER_NAME)
endif
USER_EMAIL=$(USER_NAME)@$(shell hostname -f)
PUID:=$(shell id -u)
PGID:=$(shell id -g)

# Safe defaults for testing the release process without publishing to the final/official
# hosts/indexes/registries:
RELEASE_PUBLISH=false
TOWNCRIER_COMPARE_BRANCH=develop
PYPI_REPO=testpypi
PYPI_HOSTNAME=test.pypi.org
# Determine which branch is checked out depending on the environment
GITLAB_CI=false
GITHUB_ACTIONS=false
ifeq ($(GITLAB_CI),true)
VCS_BRANCH=$(CI_COMMIT_REF_NAME)
else ifeq ($(GITHUB_ACTIONS),true)
VCS_BRANCH=$(GITHUB_REF_NAME)
else
VCS_BRANCH:=$(shell git branch --show-current)
endif
# Only publish releases from the `master` or `develop` branches:
DOCKER_PUSH=false
CI=false
GITHUB_RELEASE_ARGS=--prerelease
ifeq ($(GITLAB_CI),true)
ifeq ($(VCS_BRANCH),master)
RELEASE_PUBLISH=true
TOWNCRIER_COMPARE_BRANCH=master
PYPI_REPO=pypi
PYPI_HOSTNAME=pypi.org
DOCKER_PUSH=true
GITHUB_RELEASE_ARGS=
else ifeq ($(VCS_BRANCH),develop)
# Publish pre-releases from the `develop` branch:
RELEASE_PUBLISH=true
endif
endif
# Address undefined variables warnings when running under local development
VCS_REMOTE_PUSH_URL=
CODECOV_TOKEN=
GH_TOKEN=

# Done with `$(shell ...)`, echo recipe commands going forward
.SHELLFLAGS+= -x


## Top-level targets

.PHONY: all
### Default target
all: build

# Strive for as much consistency as possible in development tasks between the local host
# and inside containers.  To that end, most of the `*-docker` container target recipes
# should run the corresponding `*-local` local host target recipes inside the
# development container.  Top level targets, like `test`, should run as much as possible
# inside the development container.

.PHONY: build
### Set up everything for development from a checkout, local and in containers
build: ./.git/hooks/pre-commit build-local build-docker
.PHONY: build-local
### Set up for development locally, directly on the host
build-local: ./var/log/recreate.log
.PHONY: build-docker
### Set up for development in Docker containers
build-docker: ./var/log/docker-build.log
.PHONY: build-bump
### Bump the package version if on a branch that should trigger a release
build-bump: ~/.gitconfig ./var/log/recreate-build.log ./var/log/docker-build.log
ifeq ($(RELEASE_PUBLISH),true)
	set +x
ifneq ($(VCS_REMOTE_PUSH_URL),)
# Requires a Personal or Project Access Token in the GitLab CI/CD Variables.  That
# variable value should be prefixed with the token name as a HTTP `user:password`
# authentication string:
# https://stackoverflow.com/a/73426417/624787
	git remote set-url --push "origin" "$(VCS_REMOTE_PUSH_URL)"
# Fail fast if there's still no push access
	git push -o ci.skip --no-verify --tags "origin"
endif
ifneq ($(GITHUB_ACTIONS),true)
ifneq ($(GH_TOKEN),)
# Also push to the mirror with the `ci.skip` option to avoid redundant runs on the
# mirror.
	git remote add "github" \
	    "https://$(GH_TOKEN)@github.com/$(CI_PROJECT_PATH).git"
	git push -o ci.skip --no-verify --tags "github"
endif
endif
	set -x
endif
# Collect the versions involved in this release according to conventional commits
	cz_bump_args="--check-consistency --no-verify"
ifneq ($(VCS_BRANCH),master)
	cz_bump_args+=" --prerelease beta"
endif
ifeq ($(RELEASE_PUBLISH),true)
	cz_bump_args+=" --gpg-sign"
# Import the private signing key from CI secrets
	$(MAKE) ./var/log/gpg-import.log
endif
# Run first in case any input is needed from the developer
	exit_code=0
	./.tox/build/bin/cz bump $${cz_bump_args} --dry-run || exit_code=$$?
	rm -fv "./var/cz-bump-no-release.txt"
	if (( $$exit_code == 3 || $$exit_code == 21 ))
	then
# No release necessary for the commits since the last release, don't publish a release
	    echo "true" >"./var/cz-bump-no-release.txt"
	    exit
	elif (( $$exit_code != 0 ))
	then
# Commitizen returned an unexpected exit status code, fail
	    exit $$exit_code
	fi
	cz_bump_args+=" --yes"
	next_version="$$(
	    ./.tox/build/bin/cz bump $${cz_bump_args} --dry-run |
	    sed -nE 's|.* *[Vv]ersion *(.+) *→ *(.+)|\2|p'
	)"
# Update the release notes/changelog
	git fetch --no-tags origin "$(TOWNCRIER_COMPARE_BRANCH)"
	docker compose run --rm python-project-structure-devel \
	    towncrier check --compare-with "origin/$(TOWNCRIER_COMPARE_BRANCH)"
	if ! git diff --cached --exit-code
	then
	    set +x
	    echo "CRITICAL: Cannot bump version with staged changes"
	    false
	fi
# Capture the release notes for *just this* release for creating the GitHub release.
# Have to run before the real `$ towncrier build` run without the `--draft` option
# because after that the `newsfragments` will have been deleted.
	docker compose run --rm python-project-structure-devel \
	    towncrier build --version "$${next_version}" --draft --yes \
	        >"./NEWS-release.rst"
# Build and stage the release notes to be commited by `$ cz bump`
	docker compose run --rm python-project-structure-devel \
	    towncrier build --version "$${next_version}" --yes
# Increment the version in VCS
	./.tox/build/bin/cz bump $${cz_bump_args}
# Ensure the container image reflects the version bump but we don't need to update the
# requirements again.
	touch "./requirements.txt"
	$(MAKE) "./var/log/docker-build.log"

.PHONY: start
### Run the local development end-to-end stack services in the background as daemons
start: build-docker
	docker compose down
	docker compose up -d
.PHONY: run
### Run the local development end-to-end stack services in the foreground for debugging
run: build-docker
	docker compose down
	docker compose up

.PHONY: check-push
### Perform any checks that should only be run before pushing
check-push: build-docker
ifeq ($(RELEASE_PUBLISH),true)
	docker compose run --rm python-project-structure-devel \
	    towncrier check --compare-with "origin/develop"
endif

.PHONY: release
### Publish installable Python packages to PyPI and container images to Docker Hub
release: release-python
ifeq ($(RELEASE_PUBLISH),true)
	$(MAKE) release-docker
endif
.PHONY: release-python
### Publish installable Python packages to PyPI
release-python: \
		~/.pypirc ./var/log/codecov-install.log \
		./var/log/docker-build.log ./var/log/recreate-build.log
# Upload any build or test artifacts to CI/CD providers
ifeq ($(GITLAB_CI),true)
	codecov -t "$(CODECOV_TOKEN)" --file "./coverage.xml"
endif
ifeq ($(RELEASE_PUBLISH),true)
# Import the private signing key from CI secrets
	$(MAKE) ./var/log/gpg-import.log
endif
# Build Python packages/distributions from the development Docker container for
# consistency/reproducibility.
	docker compose run --rm python-project-structure-devel pyproject-build -w
# https://twine.readthedocs.io/en/latest/#using-twine
	./.tox/build/bin/twine check ./dist/* ./.tox-docker/.pkg/dist/*
	if [ ! -z "$$(git status --porcelain)" ]
	then
	    set +x
	    echo "CRITICAL: Checkout is not clean, not publishing release"
	    false
	fi
	if [ -e "./var/cz-bump-no-release.txt" ]
	then
	    exit
	fi
ifeq ($(RELEASE_PUBLISH),true)
# Publish from the local host outside a container for access to user credentials:
# https://twine.readthedocs.io/en/latest/#using-twine
# Only release on `master` or `develop` to avoid duplicate uploads
	./.tox/build/bin/twine upload -s -r "$(PYPI_REPO)" \
	    ./dist/* ./.tox-docker/.pkg/dist/*
# The VCS remote shouldn't reflect the release until the release has been successfully
# published
	git push -o ci.skip --no-verify --tags "origin" "HEAD:$(VCS_BRANCH)"
	current_version=$$(./.tox/build/bin/cz version --project)
# Create a GitLab release
	./.tox/build/bin/twine upload -s -r "gitlab" ./dist/* ./.tox-docker/.pkg/dist/*
	release_cli_args="--description ./NEWS-release.rst"
	release_cli_args+=" --tag-name v$${current_version}"
	release_cli_args+=" --assets-link {\
	\"name\":\"PyPI\",\
	\"url\":\"https://$(PYPI_HOSTNAME)/project/$(CI_PROJECT_NAME)/$${current_version}/\",\
	\"link_type\":\"package\"\
	}"
	release_cli_args+=" --assets-link {\
	\"name\":\"GitLab-PyPI-Package-Registry\",\
	\"url\":\"$(CI_SERVER_URL)/$(CI_PROJECT_PATH)/-/packages/\",\
	\"link_type\":\"package\"\
	}"
	release_cli_args+=" --assets-link {\
	\"name\":\"Docker-Hub-Container-Registry\",\
	\"url\":\"https://hub.docker.com/r/merpatterson/$(CI_PROJECT_NAME)/tags\",\
	\"link_type\":\"image\"\
	}"
	docker compose run --rm gitlab-release-cli release-cli \
	    --server-url "$(CI_SERVER_URL)" --project-id "$(CI_PROJECT_ID)" \
	    create $${release_cli_args}
# Create a GitHub release
# Ensure the tag is in place on the GitHub mirror so we can create the project host
# release object:
	git push -o ci.skip --no-verify --tags "github"
	gh release create "v$${current_version}" $(GITHUB_RELEASE_ARGS) \
	    --notes-file "./NEWS-release.rst" ./dist/* ./.tox-docker/.pkg/dist/*
endif
.PHONY: release-docker
### Publish container images to Docker Hub
release-docker: build-docker
# https://docs.docker.com/docker-hub/#step-5-build-and-push-a-container-image-to-docker-hub-from-your-computer
ifeq ($(CI),true)
	$(MAKE) ./var/log/docker-login.log
endif
	docker push "merpatterson/python-project-structure:$(VCS_BRANCH)"
	docker push "merpatterson/python-project-structure:devel-$(VCS_BRANCH)"
	docker push "$(CI_REGISTRY_IMAGE):$(VCS_BRANCH)"
	docker push "$(CI_REGISTRY_IMAGE):devel-$(VCS_BRANCH)"
	docker push "ghcr.io/rpatterson/python-project-structure:$(VCS_BRANCH)"
	docker push "ghcr.io/rpatterson/python-project-structure:devel-$(VCS_BRANCH)"
ifeq ($(VCS_BRANCH),master)
# Only update tags end users may depend on to be stable from the `master` branch
	current_version=$$(./.tox/build/bin/cz version --project)
	major_version=$$(echo $${current_version} | sed -nE 's|([0-9]+).*|\1|p')
	minor_version=$$(
	    echo $${current_version} | sed -nE 's|([0-9]+\.[0-9]+).*|\1|p'
	)
	docker push "merpatterson/python-project-structure:$${minor_version}"
	docker push "merpatterson/python-project-structure:$${major_version}"
	docker push "merpatterson/python-project-structure:latest"
	docker push "merpatterson/python-project-structure:devel"
	docker push "$(CI_REGISTRY_IMAGE):$${minor_version}"
	docker push "$(CI_REGISTRY_IMAGE):$${major_version}"
	docker push "$(CI_REGISTRY_IMAGE):latest"
	docker push "$(CI_REGISTRY_IMAGE):devel"
	docker push "ghcr.io/rpatterson/python-project-structure:$${minor_version}"
	docker push "ghcr.io/rpatterson/python-project-structure:$${major_version}"
	docker push "ghcr.io/rpatterson/python-project-structure:latest"
	docker push "ghcr.io/rpatterson/python-project-structure:devel"
	docker compose run --rm docker-pushrm
endif

.PHONY: format
### Automatically correct code in this checkout according to linters and style checkers
format: build-local
	./.tox/py3/bin/autoflake -r -i --remove-all-unused-imports \
		--remove-duplicate-keys --remove-unused-variables \
		--remove-unused-variables "./src/pythonprojectstructure/"
	./.tox/py3/bin/autopep8 -v -i -r "./src/pythonprojectstructure/"
	./.tox/py3/bin/black "./src/pythonprojectstructure/"

.PHONY: test
### Format the code and run the full suite of tests, coverage checks, and linters
test: build-docker format
# Run from the development Docker container for consistency
	docker compose run --rm python-project-structure-devel make format test-local
.PHONY: test-local
### Run the full suite of tests on the local host
test-local: build-local
	tox
.PHONY: test-docker
### Run the full suite of tests inside a docker container
test-docker: build-docker
	docker compose run --rm python-project-structure-devel make test-local
# Ensure the dist/package has been correctly installed in the image
	docker compose run --rm python-project-structure \
	    python -m pythonprojectstructure --help
	docker compose run --rm python-project-structure python-project-structure --help
.PHONY: test-debug
### Run tests in the main/default environment and invoke the debugger on errors/failures
test-debug: ./var/log/editable.log
	./.tox/py3/bin/pytest --pdb

.PHONY: upgrade
### Update all fixed/pinned dependencies to their latest available versions
upgrade:
	touch "./pyproject.toml"
	$(MAKE) PUID=$(PUID) "test"
# Update VCS hooks from remotes to the latest tag.
	./.tox/build/bin/pre-commit autoupdate

.PHONY: clean
### Restore the checkout to a state as close to an initial clone as possible
clean:
	docker compose --remove-orphans down --rmi "all" -v || true
	./.tox/build/bin/pre-commit uninstall \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push" \
	    || true
	./.tox/build/bin/pre-commit clean || true
	git clean -dfx -e "var/"
	rm -rfv "./var/log/"


## Utility targets

.PHONY: expand-template
## Create a file from a template replacing environment variables
expand-template: .SHELLFLAGS = -eu -o pipefail -c
expand-template: ./var/log/host-install.log
	if [ -e "$(target)" ]
	then
	    diff -u "$(target)" "$(template)" || true
	    echo "ERROR: Template $(template) has been updated:"
	    echo "       Reconcile changes and \`$$ touch $(target)\`:"
	    false
	fi
	envsubst <"$(template)" >"$(target)"


## Real targets

./requirements.txt: ./pyproject.toml ./setup.cfg ./tox.ini ./requirements-build.txt.in
	$(MAKE) "./var/log/recreate-build.log"
ifeq ($(CI),true)
# Don't update dependencies in CI/CD so that the release of new versions don't break
# CI/CD runs.
	touch "$(@)"
else
# Only upgrade dependencies locally during local development to ensure changes in
# dependencies are reflected in the frozen versions and to notify developers that new
# versions are available.
	tox -e "build"
endif

./var/log/recreate.log: \
		./var/log/host-install.log \
		./requirements.txt ./requirements-devel.txt ./tox.ini
	mkdir -pv "$(dir $(@))"
# Prevent uploading unintended distributions
	rm -vf ./dist/* ./.tox/.pkg/dist/* | tee -a "$(@)"
	tox -r --notest -v | tee -a "$(@)"
# Workaround tox's `usedevelop = true` not working with `./pyproject.toml`
./var/log/editable.log: ./var/log/recreate.log
	./.tox/py3/bin/pip install -e "./" | tee -a "$(@)"
./var/log/recreate-build.log: \
		./var/log/host-install.log ./requirements-build.txt ./tox.ini
	mkdir -pv "$(dir $(@))"
	tox -r -e "build" --notest -v | tee -a "$(@)"

# Docker targets
./var/log/docker-build.log: \
		./Dockerfile ./Dockerfile.devel ./.dockerignore \
		./requirements.txt ./requirements-devel.txt ./bin/entrypoint \
		./docker-compose.yml ./docker-compose.override.yml ./.env \
		./var/log/recreate-build.log
# Ensure access permissions to build artifacts in container volumes.
# If created by `# dockerd`, they end up owned by `root`.
	mkdir -pv "$(dir $(@))" "./var-docker/log/" "./.tox/" "./.tox-docker/" \
	    "./src/python_project_structure.egg-info/" \
	    "./src/python_project_structure-docker.egg-info/"
# Workaround issues with local images and the development image depending on the end
# user image.  It seems that `depends_on` isn't sufficient.
	current_version=$$(./.tox/build/bin/cz version --project)
# https://github.com/moby/moby/issues/39003#issuecomment-879441675
	docker_build_args=" \
	    --build-arg BUILDKIT_INLINE_CACHE=1 \
	    --build-arg VERSION=$${current_version}"
	docker_build_user_tags=" \
	    --tag merpatterson/python-project-structure:local \
	    --tag merpatterson/python-project-structure:$(VCS_BRANCH) \
	    --tag merpatterson/python-project-structure:$${current_version}\
	    --tag $(CI_REGISTRY_IMAGE):$(VCS_BRANCH) \
	    --tag $(CI_REGISTRY_IMAGE):$${current_version}\
	    --tag ghcr.io/rpatterson/python-project-structure:$(VCS_BRANCH) \
	    --tag ghcr.io/rpatterson/python-project-structure:$${current_version}"
ifeq ($(VCS_BRANCH),master)
# Only update tags end users may depend on to be stable from the `master` branch
	major_version=$$(echo $${current_version} | sed -nE 's|([0-9]+).*|\1|p')
	minor_version=$$(
	    echo $${current_version} | sed -nE 's|([0-9]+\.[0-9]+).*|\1|p'
	)
	docker_build_user_tags+=" \
	    --tag merpatterson/python-project-structure:$${minor_version} \
	    --tag merpatterson/python-project-structure:$${major_version} \
	    --tag merpatterson/python-project-structure:latest \
	    --tag $(CI_REGISTRY_IMAGE):$${minor_version} \
	    --tag $(CI_REGISTRY_IMAGE):$${major_version} \
	    --tag $(CI_REGISTRY_IMAGE):latest \
	    --tag ghcr.io/rpatterson/python-project-structure:$${minor_version} \
	    --tag ghcr.io/rpatterson/python-project-structure:$${major_version} \
	    --tag ghcr.io/rpatterson/python-project-structure:latest"
endif
	docker_build_caches=""
ifeq ($(GITLAB_CI),true)
# Don't cache when building final releases on `master`
ifneq ($(VCS_BRANCH),master)
	docker pull "$(CI_REGISTRY_IMAGE):$(VCS_BRANCH)" || true
	docker_build_caches+=" --cache-from $(CI_REGISTRY_IMAGE):$(VCS_BRANCH)"
endif
endif
ifeq ($(GITHUB_ACTIONS),true)
ifneq ($(VCS_BRANCH),master)
# Can't use the GitHub Actions cache when we're only pushing images from GitLab CI/CD
	docker pull "ghcr.io/rpatterson/python-project-structure:$(VCS_BRANCH)" || true
	docker_build_caches+=" --cache-from \
	    ghcr.io/rpatterson/python-project-structure:$(VCS_BRANCH)"
endif
endif
	docker buildx build --pull $${docker_build_args} $${docker_build_user_tags} \
	    $${docker_build_caches} "./" | tee -a "$(@)"
# Build the development image
	docker_build_caches=""
ifeq ($(GITLAB_CI),true)
ifneq ($(VCS_BRANCH),master)
	docker pull "$(CI_REGISTRY_IMAGE):devel-$(VCS_BRANCH)" || true
	docker_build_caches+=" --cache-from $(CI_REGISTRY_IMAGE):devel-$(VCS_BRANCH)"
endif
endif
ifeq ($(GITHUB_ACTIONS),true)
ifneq ($(VCS_BRANCH),master)
	docker pull "ghcr.io/rpatterson/python-project-structure:devel-$(VCS_BRANCH)" || true
	docker_build_caches+=" --cache-from \
	    ghcr.io/rpatterson/python-project-structure:devel-$(VCS_BRANCH)"
endif
endif
	docker buildx build $${docker_build_args} $${docker_build_caches} \
	    --tag "merpatterson/python-project-structure:devel" \
	    --tag "merpatterson/python-project-structure:devel-$(VCS_BRANCH)" \
	    --tag "$(CI_REGISTRY_IMAGE):devel" \
	    --tag "$(CI_REGISTRY_IMAGE):devel-$(VCS_BRANCH)" \
	    --tag "ghcr.io/rpatterson/python-project-structure:devel" \
	    --tag "ghcr.io/rpatterson/python-project-structure:devel-$(VCS_BRANCH)" \
	    --file "./Dockerfile.devel" "./" | tee -a "$(@)"

# Local environment variables from a template
./.env: ./.env.in
	$(MAKE) "PUID=$(PUID)" "PGID=$(PGID)" \
	    "template=$(<)" "target=$(@)" expand-template

# Perform any one-time local checkout set up
./var/log/host-install.log:
	mkdir -pv "$(dir $(@))"
# Bootstrap the minimum Python environment
	(
	    if ! which pip
	    then
	        if which apk
	        then
	            sudo apk update
	            sudo apk add "gettext" "py3-pip" "gnupg" "github-cli" "curl"
	        elif which apt-get
	        then
	            sudo apt-get update
	            sudo apt-get install -y \
	                "gettext-base" "python3-pip" "gnupg" "gh" "curl"
	        else
	            set +x
	            echo "ERROR: OS not supported for installing host dependencies"
	            false
	        fi
	    fi
	    which tox || pip install tox
	) | tee -a "$(@)"
./var/log/codecov-install.log:
	mkdir -pv "$(dir $(@))"
# Install the code test coverage publishing tool
	(
	    if ! which codecov
	    then
	        mkdir -pv ~/.local/bin/
# https://docs.codecov.com/docs/codecov-uploader#using-the-uploader-with-codecovio-cloud
	        if which brew
	        then
# Mac OS X
	            curl --output-dir ~/.local/bin/ -Os \
	                "https://uploader.codecov.io/latest/macos/codecov"
	        elif which apk
	        then
# Alpine
	            wget --directory-prefix ~/.local/bin/ \
	                "https://uploader.codecov.io/latest/alpine/codecov"
	        else
# Other Linux distributions
	            curl --output-dir ~/.local/bin/ -Os \
	                "https://uploader.codecov.io/latest/linux/codecov"
	        fi
	        chmod +x ~/.local/bin/codecov
	    fi
	    if ! which codecov
	    then
	        set +x
	        echo "ERROR: CodeCov CLI tool still not on PATH"
	        false
	    fi
	) | tee -a "$(@)"

./.git/hooks/pre-commit: ./var/log/recreate.log
	./.tox/build/bin/pre-commit install \
	    --hook-type "pre-commit" --hook-type "commit-msg" --hook-type "pre-push"

# Capture any project initialization tasks for reference.  Not actually usable.
 ./pyproject.toml:
	./.tox/build/bin/cz init

# Emacs editor settings
./.dir-locals.el: ./.dir-locals.el.in
	$(MAKE) "template=$(<)" "target=$(@)" expand-template

# User-created pre-requisites
~/.gitconfig:
	git config --global user.name "$(USER_FULL_NAME)"
	git config --global user.email "$(USER_EMAIL)"
~/.pypirc: ./home/.pypirc.in
	$(MAKE) "template=$(<)" "target=$(@)" expand-template
./var/log/docker-login.log:
	printenv "DOCKER_PASS" | docker login -u "merpatterson" --password-stdin |
	    tee -a "$(@)"
	printenv "CI_REGISTRY_PASSWORD" |
	    docker login -u "$(CI_REGISTRY_USER)" --password-stdin "$(CI_REGISTRY)"
	printenv "GH_TOKEN" |
	    docker login -u "$(GITHUB_REPOSITORY_OWNER)" --password-stdin "ghcr.io"

# GPG signing key creation and management in CI
export GPG_PASSPHRASE=
./var/ci-cd-signing-subkey.asc:
# We need a private key in the CI/CD environment for signing release commits and
# artifacts.  Use a subkey so that it can be revoked without affecting your main key.
# This recipe captures what I had to do to export a private signing subkey.  It's not
# widely tested so it should probably only be used for reference.  It worked for me but
# the risk is leaking your main private key so double and triple check all your
# assumptions and results.
# 1. Create a signing subkey with a NEW, SEPARATE passphrase:
#    https://wiki.debian.org/Subkeys#How.3F
# 2. Get the long key ID for that private subkey:
#	gpg --list-secret-keys --keyid-format "LONG"
# 3. Export *just* that private subkey and verify that the main secret key packet is the
#    GPG dummy packet and that the only other private key included is the intended
#    subkey:
#	gpg --armor --export-secret-subkeys "$(GPG_SIGNING_KEYID)!" |
#	    gpg --list-packets
# 4. Export that key as text to a file:
	gpg --armor --export-secret-subkeys "$(GPG_SIGNING_KEYID)!" >"$(@)"
# 5. Confirm that the exported key can be imported into a temporary GNU PG directory and
#    that temporary directory can then be used to sign files:
#	gnupg_homedir=$$(mktemp -d --suffix=".d" "gnupd.XXXXXXXXXX")
#	printenv 'GPG_PASSPHRASE' >"$${gnupg_homedir}/.passphrase"
#	gpg --homedir "$${gnupg_homedir}" --batch --import <"$(@)"
#	echo "Test signature content" >"$${gnupg_homedir}/test-sig.txt"
#	gpgconf --kill gpg-agent
#	gpg --homedir "$${gnupg_homedir}" --batch --pinentry-mode "loopback" \
#	    --passphrase-file "$${gnupg_homedir}/.passphrase" \
#	    --local-user "$(GPG_SIGNING_KEYID)!" --sign "$${gnupg_homedir}/test-sig.txt"
#	gpg --batch --verify "$${gnupg_homedir}/test-sig.txt.gpg"
# 6. Add the contents of this target as a `GPG_SIGNING_PRIVATE_KEY` secret in CI and the
# passphrase for the signing subkey as a `GPG_PASSPHRASE` secret in CI
./var/log/gpg-import.log:
# In each CI run, import the private signing key from the CI secrets
	printenv "GPG_SIGNING_PRIVATE_KEY" | gpg --batch --import | tee -a "$(@)"
	echo 'default-key:0:"$(GPG_SIGNING_KEYID)' | gpgconf —change-options gpg
	git config --global user.signingkey "$(GPG_SIGNING_KEYID)"
# "Unlock" the signing key for the remainder of this CI run:
	printenv 'GPG_PASSPHRASE' >"./var/ci-cd-signing-subkey.passphrase"
	true | gpg --batch --pinentry-mode "loopback" \
	    --passphrase-file "./var/ci-cd-signing-subkey.passphrase" \
	    --sign | gpg --list-packets
