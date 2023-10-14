# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

## Container image in which to build, test, and release the project

# I *want* something to break to let me know if something changes in the latest version
# of the base image changes something:
# hadolint ignore=DL3007
FROM docker:latest

# Least volatile layers first:

# Project constants:
ARG PROJECT_NAMESPACE=rpatterson
ARG PROJECT_NAME=project-structure

# https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys
LABEL org.opencontainers.image.url="https://gitlab.com/${PROJECT_NAMESPACE}/${PROJECT_NAME}"
LABEL org.opencontainers.image.documentation="https://gitlab.com/${PROJECT_NAMESPACE}/${PROJECT_NAME}"
LABEL org.opencontainers.image.source="https://gitlab.com/${PROJECT_NAMESPACE}/${PROJECT_NAME}"
LABEL org.opencontainers.image.title="Project Structure Build Host"
LABEL org.opencontainers.image.description="Project structure foundation or template, build host"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.authors="Ross Patterson <me@rpatterson.net>"
LABEL org.opencontainers.image.vendor="rpatterson.net"
LABEL org.opencontainers.image.base.name="docker.io/library/docker:latest"
# Build-time labels:
LABEL org.opencontainers.image.version=0.0.1

# Find the same home directory even when run as another user, for example `root`:
ENV PROJECT_NAMESPACE="${PROJECT_NAMESPACE}"
ENV PROJECT_NAME="${PROJECT_NAME}"
ENV HOME="/home/runner"
ENV PATH="${HOME}/.local/state/${PROJECT_NAME}/bin:${HOME}/.local/bin:${PATH}"

ENTRYPOINT [ "docker-entrypoint.sh", "entrypoint" ]
CMD [ "make", "-e", "build-docker" ]

# More volatile layers and layers with longer build times last:

# Install the operating system packages needed to use the `./Makefile`.  Also install
# any operating system packages the `./Makefile` might install to optimize build times:
# hadolint ignore=DL3018
RUN \
    apk add --no-cache \
    "make" \
    "bash" \
    "su-exec" \
    "git" \
    "gettext" \
    "py3-pip" \
    "gnupg" \
    "curl" \
    "github-cli" \
    && rm -rf /var/cache/apk/*

# Reflect that the container image already has all build dependencies installed and
# install tox locally:
COPY [ "./requirements.txt.in", "${HOME}/.local/state/${PROJECT_NAME}/lib/" ]
RUN mkdir -pv "${HOME}/.local/state/${PROJECT_NAME}/log/" && \
    date >"${HOME}/.local/state/${PROJECT_NAME}/log/host-install.log" && \
    python3 -m venv "${HOME}/.local/state/${PROJECT_NAME}/" && \
    "${HOME}/.local/state/${PROJECT_NAME}/bin/pip" install --force-reinstall -r \
        "${HOME}/.local/state/${PROJECT_NAME}/lib/requirements.txt.in"

COPY [ "./bin/entrypoint", "/usr/local/bin/entrypoint" ]
