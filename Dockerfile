# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT


## Image layers shared between all variants.

# Stay as close to a vanilla environment as possible:
FROM buildpack-deps:stable AS base

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
LABEL org.opencontainers.image.base.name="docker.io/library/buildpack-deps"

# Find the same home directory even when run as another user, e.g. `root`.
ENV HOME="/home/project-structure"
WORKDIR "/home/project-structure/"
ENTRYPOINT [ "entrypoint" ]

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

# Build-time `LABEL`s
ARG VERSION=
LABEL org.opencontainers.image.version=${VERSION}


## Container image for use by end users.

# Stay as close to a vanilla environment as possible:
FROM base AS user

# TEMPLATE: Add image setup specific to the end user image that is created by the
# development image, usually installable packages.


## Container image for use by developers.

# Stay as close to the end user image as possible for build cache efficiency.
FROM base AS devel

# Least volatile layers first:
LABEL org.opencontainers.image.title="Project Structure Development"
LABEL org.opencontainers.image.description="Project structure foundation or template, development image"

# Remain in the checkout `WORKDIR` and make the build tools the default
# command to run.
WORKDIR "/usr/local/src/project-structure/"
CMD [ "tox" ]

# Then add everything that might contribute to efficient development.
# Include Python build tools:
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get install --no-install-recommends -y tox=3.21.4-1
