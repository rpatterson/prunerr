## Container image for use by end users

# Stay as close to a vanilla Python environment as possible
ARG PYTHON_MINOR=3.10
FROM python:${PYTHON_MINOR}

ARG PYTHON_ENV=py310
ARG VERSION=
ARG PYTHON_WHEEL

RUN \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' \
    >"/etc/apt/apt.conf.d/keep-cache"
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install --no-install-recommends -y gosu=1.12-1+b6
# Put the `ENTRYPOINT` on the `$PATH`
COPY [ "./bin/entrypoint", "/usr/local/bin/entrypoint" ]

WORKDIR "/usr/local/src/prunerr/"
# Install dependencies with fixed versions in a separate layer to optimize build times
# because this step takes the most time and changes the least frequently.
COPY [ "./requirements/${PYTHON_ENV}/user.txt", "./requirements/${PYTHON_ENV}/" ]
# hadolint ignore=DL3042
RUN --mount=type=cache,target=/root/.cache,sharing=locked \
    pip install -r "./requirements/${PYTHON_ENV}/user.txt"
# Install this package in the most common/standard Python way while still being able to
# build the image locally.
COPY [ "${PYTHON_WHEEL}", "${PYTHON_WHEEL}" ]
# hadolint ignore=DL3013,DL3042
RUN --mount=type=cache,target=/root/.cache,sharing=locked \
    pip install "${PYTHON_WHEEL}" && \
    rm -rfv "./dist/"

# Find the same configuration file even when run as another user, e.g. `root`.
ENV HOME="/home/prunerr/"
WORKDIR "/home/prunerr/"
ENTRYPOINT [ "entrypoint" ]
CMD [ "prunerr", "daemon" ]

# https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys
LABEL org.opencontainers.image.url="https://gitlab.com/rpatterson/prunerr"
LABEL org.opencontainers.image.documentation="https://gitlab.com/rpatterson/prunerr"
LABEL org.opencontainers.image.source="https://gitlab.com/rpatterson/prunerr"
LABEL org.opencontainers.image.title="Prunerr"
LABEL org.opencontainers.image.description="Remove Servarr download client items to preserve disk space according to rules."
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.authors="Ross Patterson <me@rpatterson.net>"
LABEL org.opencontainers.image.vendor="rpatterson.net"
LABEL org.opencontainers.image.base.name="docker.io/library/python:${PYTHON_MINOR}"
# Build-time `LABEL`s
LABEL org.opencontainers.image.version=${VERSION}
