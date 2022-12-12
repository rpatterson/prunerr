## Container image for use by end users

# Stay as close to a vanilla Python environment as possible
FROM python:3

ARG VERSION=

# Put the `ENTRYPOINT` on the `$PATH`
RUN apt-get update && apt-get install -y gosu && rm -rf /var/lib/apt/lists/*
COPY [ "./bin/entrypoint", "/usr/local/bin/entrypoint" ]

WORKDIR "/usr/local/src/prunerr/"
# Install dependencies with fixed versions in a separate layer to optimize build times
# because this step takes the most time and changes the least frequently.
COPY [ "./requirements.txt", "./" ]
RUN pip install --no-cache-dir -r "./requirements.txt"
# Install this package in the most common/standard Python way while still being able to
# build the image locally.
RUN --mount=source=./,target=./,rw,type=bind pip install --no-cache-dir "./"

# Find the same configuration file even when run as another user, e.g. `root`.
ENV HOME="/home/prunerr/"
WORKDIR "/home/prunerr/"
ENTRYPOINT [ "entrypoint" ]
CMD [ "prunerr", "daemon" ]

# https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys
LABEL org.opencontainers.image.url="https://gitlab.com/rpatterson/prunerr"
LABEL org.opencontainers.image.documentation="https://gitlab.com/rpatterson/prunerr"
LABEL org.opencontainers.image.source="https://gitlab.com/rpatterson/prunerr"
LABEL org.opencontainers.image.title="prunerr"
LABEL org.opencontainers.image.description="Remove Servarr download client items to preserve disk space according to rules."
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.authors="Ross Patterson <me@rpatterson.net>"
LABEL org.opencontainers.image.vendor="rpatterson.net"
LABEL org.opencontainers.image.base.name="docker.io/library/python:3"
# Build-time `LABEL`s
LABEL org.opencontainers.image.version=${VERSION}
