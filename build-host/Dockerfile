# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

## Container image in which to build, test, and release projects.

# I *want* something to break to let me know if something changes in the latest version
# of the base image changes something:
# hadolint ignore=DL3007
FROM docker:latest

# Least volatile layers first:

# Project constants:
# TEMPLATE: Only change these if you customize this image.  Otherwise use the version of
# this image from the project template in your CI/CD.
ARG PROJECT_NAMESPACE=rpatterson
ARG PROJECT_NAME=project-structure

# https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys
LABEL org.opencontainers.image.url="https://gitlab.com/${PROJECT_NAMESPACE}/${PROJECT_NAME}"
LABEL org.opencontainers.image.documentation="https://gitlab.com/${PROJECT_NAMESPACE}/${PROJECT_NAME}/-/blob/develop/build-host/README.rst"
LABEL org.opencontainers.image.source="https://gitlab.com/${PROJECT_NAMESPACE}/${PROJECT_NAME}/-/blob/develop/build-host/Dockerfile"
LABEL org.opencontainers.image.title="Project Structure Build Host"
LABEL org.opencontainers.image.description="Container image in which to build, test, and release projects."
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.authors="Ross Patterson <me@rpatterson.net>"
LABEL org.opencontainers.image.vendor="rpatterson.net"
LABEL org.opencontainers.image.base.name="docker.io/library/docker:latest"
# Build-time labels:
LABEL org.opencontainers.image.version=1.0.0

# Find the same home directory even when run as another user, for example `root`:
ENV PROJECT_NAMESPACE="${PROJECT_NAMESPACE}"
ENV PROJECT_NAME="${PROJECT_NAME}"
ENV HOME="/home/runner"
ENV PATH="${HOME}/.local/bin:${PATH}"
# Prevent Node Version Manager (NVM) installing into `/bin/versions/**`:
ENV NVM_DIR="${HOME}/.nvm"
# Node.js releases compatible with Alpine Linux based on musl libc:
# https://github.com/nvm-sh/nvm/issues/1102#issuecomment-550572252
ENV NVM_NODEJS_ORG_MIRROR="https://unofficial-builds.nodejs.org/download/release"

ENTRYPOINT [ "docker-entrypoint.sh", "init-job.sh", "entrypoint.sh" ]
CMD [ "make", "-e", "build-docker" ]

# More volatile layers and layers with longer build times last:

# Install the operating system packages needed to use the `./Makefile`.  Also install
# any operating system packages the `./Makefile` might install to optimize build times:
# hadolint ignore=DL3018
RUN \
    apk add --no-cache \
    "coreutils" \
    "make" \
    "bash" \
    "su-exec" \
    "git" \
    "gettext" \
    "grep" \
    "py3-pip" \
    "gnupg" \
    "curl" \
    "tar" \
    "github-cli" \
    && rm -rf /var/cache/apk/*

# Bake external build dependencies into the image:
COPY [ "./bin/install-codecov.sh", "${HOME}/.local/bin/" ]
# hadolint ignore=DL3042,DL4006,SC1091
RUN --mount=type=cache,target=/root/.cache,sharing=locked \
    pip3 install --user "pipx==1.2.0" && \
    python3 -m "pipx" ensurepath && \
    pipx install "tox==4.11.3" && \
    wget -qO- "https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.3/install.sh" | \
        bash && \
    echo 'nvm_get_arch() { nvm_echo x64-musl; }' >>"${HOME}/.nvm/nvm.sh" && \
	. "${HOME}/.nvm/nvm.sh" || true && \
    nvm install "18" && \
    ${HOME}/.local/bin/install-codecov.sh && \
    git config -f "${HOME}/.gitconfig" "user.name" "CI Runner" && \
    git config -f "${HOME}/.gitconfig" "user.email" \
    "runner@build-host.${PROJECT_NAMESPACE:-rpatterson}.localhost" && \
    mkdir -pv "${HOME}/.local/state/${PROJECT_NAME}/log/"

COPY [ "./bin/init-job.sh",  "./bin/entrypoint.sh", "/usr/local/bin/" ]
