# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT


## Image layers shared between all variants.

# Stay as close to an un-customized environment as possible:
ARG PYTHON_MINOR=3.11
FROM python:${PYTHON_MINOR} AS base
# Defensive shell options:
SHELL ["/bin/bash", "-eu", "-o", "pipefail", "-c"]

# Project constants:
ARG PROJECT_NAMESPACE=rpatterson
ARG PROJECT_NAME=project-structure

# Least volatile layers first:
# https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys
LABEL org.opencontainers.image.url="https://gitlab.com/${PROJECT_NAMESPACE}/${PROJECT_NAME}"
LABEL org.opencontainers.image.documentation="https://gitlab.com/${PROJECT_NAMESPACE}/${PROJECpT_NAME}"
LABEL org.opencontainers.image.source="https://gitlab.com/${PROJECT_NAMESPACE}/${PROJECT_NAME}"
LABEL org.opencontainers.image.title="Project Structure"
LABEL org.opencontainers.image.description="Project structure foundation or template"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.authors="Ross Patterson <me@rpatterson.net>"
LABEL org.opencontainers.image.vendor="rpatterson.net"
LABEL org.opencontainers.image.base.name="docker.io/library/python:${PYTHON_MINOR}"

# Find the same home directory even when run as another user, for example `root`.
ENV PROJECT_NAMESPACE="${PROJECT_NAMESPACE}"
ENV PROJECT_NAME="${PROJECT_NAME}"
ENV HOME="/home/${PROJECT_NAME}"
WORKDIR "${HOME}"
ENTRYPOINT [ "entrypoint.sh" ]
CMD [ "project-structure" ]

# Support for a volume to preserve data between runs and share data between variants:
# TEMPLATE: Add other user `${HOME}/` files to preserved.
RUN mkdir -pv "${HOME}/.local/share/${PROJECT_NAME}/" && \
    touch "${HOME}/.local/share/${PROJECT_NAME}/bash_history" && \
    ln -snv --relative "${HOME}/.local/share/${PROJECT_NAME}/bash_history" \
        "${HOME}/.bash_history"

# Put the `ENTRYPOINT` on the `$PATH`
COPY [ "./bin/entrypoint.sh", "/usr/local/bin/" ]

# Install operating system packages needed for the image `ENDPOINT`:
RUN \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' \
    >"/etc/apt/apt.conf.d/keep-cache"
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install --no-install-recommends -y "gosu=1.14-1+b6"

WORKDIR "/usr/local/src/${PROJECT_NAME}/"
# Install dependencies with fixed versions in a separate layer to optimize build times
# because this step takes the most time and changes the least often.
ARG PYTHON_ENV=py311
COPY [ "./requirements/${PYTHON_ENV}/user.txt", "./requirements/${PYTHON_ENV}/" ]
# hadolint ignore=DL3042
RUN --mount=type=cache,target=/root/.cache,sharing=locked \
    pip3 install -r "./requirements/${PYTHON_ENV}/user.txt"

# Build-time labels:
ARG VERSION=
LABEL org.opencontainers.image.version=${VERSION}


## Container image for use by end users.

# Stay as close to an un-customized environment as possible:
FROM base AS user
# Defensive shell options:
SHELL ["/bin/bash", "-eu", "-o", "pipefail", "-c"]

# Least volatile layers first:
WORKDIR "/home/${PROJECT_NAME}/"

# Install this package in the most common/standard Python way while still being able to
# build the image locally.
ARG PYTHON_WHEEL
COPY [ "${PYTHON_WHEEL}", "${PYTHON_WHEEL}" ]
# hadolint ignore=DL3013,DL3042
RUN --mount=type=cache,target=/root/.cache,sharing=locked \
    pip3 install "${PYTHON_WHEEL}" && \
    rm -rfv "./dist/"


## Container image for use by developers.

# Stay as close to the user image as possible for build cache efficiency:
FROM base AS devel
# Defensive shell options:
SHELL ["/bin/bash", "-eu", "-o", "pipefail", "-c"]

# Least volatile layers first:
LABEL org.opencontainers.image.title="Project Structure Development"
LABEL org.opencontainers.image.description="Project structure foundation or template, development image"

# Activate the Python virtual environment
ENV VIRTUAL_ENV="/usr/local/src/${PROJECT_NAME}/.tox/${PYTHON_ENV}"
ENV PATH="${VIRTUAL_ENV}/bin:${HOME}/.local/bin:${PATH}"
# Remain in the checkout `WORKDIR` and make the build tools the default
# command to run.
ENV PATH="${HOME}/.local/bin:${PATH}"
WORKDIR "/usr/local/src/${PROJECT_NAME}/"
# Have to use the shell form of `CMD` because it needs variable substitution:
# hadolint ignore=DL3025
CMD tox -e "${PYTHON_ENV}"

# Bake in tools used in the inner loop of the development cycle:
COPY [ "./Makefile", "./" ]
RUN --mount=type=cache,target=/root/.cache,sharing=locked \
    make "${HOME}/.local/bin/tox"
