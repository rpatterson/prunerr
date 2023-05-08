# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT


## Image layers shared between all variants.

# Stay as close to a vanilla Python environment as possible
ARG PYTHON_MINOR=3.10
FROM python:${PYTHON_MINOR} AS base
# Defensive shell options:
SHELL ["/bin/bash", "-eu", "-o", "pipefail", "-c"]

# Least volatile layers first:
# https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys
LABEL org.opencontainers.image.url="https://gitlab.com/rpatterson/project-structure"
LABEL org.opencontainers.image.documentation="https://gitlab.com/rpatterson/project-structure"
LABEL org.opencontainers.image.source="https://gitlab.com/rpatterson/project-structure"
LABEL org.opencontainers.image.title="Project Structure"
LABEL org.opencontainers.image.description="Project structure foundation or template"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.authors="Ross Patterson <me@rpatterson.net>"
LABEL org.opencontainers.image.vendor="rpatterson.net"
LABEL org.opencontainers.image.base.name="docker.io/library/python:${PYTHON_MINOR}"

# Find the same home directory even when run as another user, e.g. `root`.
ENV HOME="/home/project-structure"
ENTRYPOINT [ "entrypoint" ]
CMD [ "project-structure" ]

# Put the `ENTRYPOINT` on the `$PATH`
COPY [ "./bin/entrypoint", "/usr/local/bin/entrypoint" ]

# Install OS packages needed for the image `ENDPOINT`:
RUN \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' \
    >"/etc/apt/apt.conf.d/keep-cache"
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install --no-install-recommends -y "gosu=1.12-1+b6"

WORKDIR "/usr/local/src/project-structure/"
# Install dependencies with fixed versions in a separate layer to optimize build times
# because this step takes the most time and changes the least frequently.
ARG PYTHON_ENV=py310
COPY [ "./requirements/${PYTHON_ENV}/user.txt", "./requirements/${PYTHON_ENV}/" ]
# hadolint ignore=DL3042
RUN --mount=type=cache,target=/root/.cache,sharing=locked \
    pip3 install -r "./requirements/${PYTHON_ENV}/user.txt"

# Build-time `LABEL`s
ARG VERSION=
LABEL org.opencontainers.image.version=${VERSION}


## Container image for use by end users.

# Stay as close to a vanilla environment as possible:
FROM base AS user
# Defensive shell options:
SHELL ["/bin/bash", "-eu", "-o", "pipefail", "-c"]

# Least volatile layers first:
WORKDIR "/home/project-structure/"

# Install this package in the most common/standard Python way while still being able to
# build the image locally.
ARG PYTHON_WHEEL
COPY [ "${PYTHON_WHEEL}", "${PYTHON_WHEEL}" ]
# hadolint ignore=DL3013,DL3042
RUN --mount=type=cache,target=/root/.cache,sharing=locked \
    pip3 install "${PYTHON_WHEEL}" && \
    rm -rfv "./dist/"


## Container image for use by developers.

# Stay as close to the end user image as possible for build cache efficiency:
FROM base AS devel
# Defensive shell options:
SHELL ["/bin/bash", "-eu", "-o", "pipefail", "-c"]

# Least volatile layers first:
LABEL org.opencontainers.image.title="Project Structure Development"
LABEL org.opencontainers.image.description="Project structure foundation or template, development image"

# Activate the Python virtual environment
ENV VIRTUAL_ENV="/usr/local/src/project-structure/.tox/${PYTHON_ENV}"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"
# Remain in the checkout `WORKDIR` and make the build tools the default
# command to run.
WORKDIR "/usr/local/src/project-structure/"
# Have to use the shell form of `CMD` because we need variable substitution:
# hadolint ignore=DL3025
CMD tox -e "${PYTHON_ENV}"

# Then add everything that might contribute to efficient development.

# Simulate the parts of the host install process from `./Makefile` needed for
# development in the image:
COPY [ "./build-host/requirements.txt.in", "./build-host/" ]
# hadolint ignore=DL3042
RUN --mount=type=cache,target=/root/.cache,sharing=locked \
    mkdir -pv "${HOME}/.local/var/log/" && \
    pip3 install -r "./build-host/requirements.txt.in" | \
        tee -a "${HOME}/.local/var/log/project-structure-host-install.log"

# Match local development tool chain and avoid time consuming redundant package
# installs.  Initialize the `$ tox -e py3##` Python virtual environment to install this
# package and all the development tools into the image:
COPY [ \
    "./requirements/${PYTHON_ENV}/test.txt", \
    "./requirements/${PYTHON_ENV}/devel.txt", \
    "./requirements/${PYTHON_ENV}/" \
]
COPY [ "./tox.ini", "./" ]
RUN --mount=type=cache,target=/root/.cache,sharing=locked \
    tox --no-recreate-pkg --skip-pkg-install --notest -e "${PYTHON_ENV}"
