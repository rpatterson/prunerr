# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT


## Image layers shared between all variants.

# Stay as close to an un-customized environment as possible:
FROM buildpack-deps:stable AS base
# Defensive shell options:
SHELL ["/bin/bash", "-eu", "-o", "pipefail", "-c"]

# Project constants:
ARG PROJECT_NAMESPACE=rpatterson
ARG PROJECT_NAME=project-structure

# Least volatile layers first:
# https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys
LABEL org.opencontainers.image.url="https://gitlab.com/${PROJECT_NAMESPACE}/${PROJECT_NAME}"
LABEL org.opencontainers.image.documentation="https://gitlab.com/${PROJECT_NAMESPACE}/${PROJECT_NAME}"
LABEL org.opencontainers.image.source="https://gitlab.com/${PROJECT_NAMESPACE}/${PROJECT_NAME}"
LABEL org.opencontainers.image.title="Project Structure"
LABEL org.opencontainers.image.description="Project structure foundation or template"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.authors="Ross Patterson <me@rpatterson.net>"
LABEL org.opencontainers.image.vendor="rpatterson.net"
LABEL org.opencontainers.image.base.name="docker.io/library/buildpack-deps"

# Find the same home directory even when run as another user, for example `root`.
ENV PROJECT_NAMESPACE="${PROJECT_NAMESPACE}"
ENV PROJECT_NAME="${PROJECT_NAME}"
ENV HOME="/home/${PROJECT_NAME}"
WORKDIR "${HOME}"
ENTRYPOINT [ "entrypoint" ]
CMD [ "bash" ]

# Support for a volume to preserve data between runs and share data between variants:
# TEMPLATE: Add other user `${HOME}/` files to preserved.
RUN mkdir -pv "${HOME}/.local/share/${PROJECT_NAME}/" && \
    touch "${HOME}/.local/share/${PROJECT_NAME}/bash_history" && \
    ln -snv --relative "${HOME}/.local/share/${PROJECT_NAME}/bash_history" \
        "${HOME}/.bash_history"

# Put the `ENTRYPOINT` on the `$PATH`
COPY [ "./bin/entrypoint", "/usr/local/bin/entrypoint" ]

# Install operating system packages needed for the image `ENDPOINT`:
RUN \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' \
    >"/etc/apt/apt.conf.d/keep-cache"
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install --no-install-recommends -y "gosu=1.14-1+b6"

# Build-time labels:
ARG VERSION=
LABEL org.opencontainers.image.version=${VERSION}


## Container image for use by end users.

# Stay as close to an un-customized environment as possible:
FROM base AS user
# Defensive shell options:
SHELL ["/bin/bash", "-eu", "-o", "pipefail", "-c"]

# TEMPLATE: Add image setup specific to the user image, often installable packages built
# from the project.


## Container image for use by developers.

# Stay as close to the user image as possible for build cache efficiency:
FROM base AS devel
# Defensive shell options:
SHELL ["/bin/bash", "-eu", "-o", "pipefail", "-c"]

# Least volatile layers first:
LABEL org.opencontainers.image.title="Project Structure Development"
LABEL org.opencontainers.image.description="Project structure foundation or template, development image"

# Remain in the checkout `WORKDIR` and make the build tools the default
# command to run.
ENV PATH="${HOME}/.local/state/${PROJECT_NAME}/bin:${HOME}/.local/bin:${PATH}"
WORKDIR "/usr/local/src/${PROJECT_NAME}/"

# TEMPLATE: Add image setup specific to the development for this project type, often at
# least installing development tools.
