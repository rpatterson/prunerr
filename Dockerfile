## Container image for use by end users

# Stay as close to a vanilla Python environment as possible
ARG PYTHON_MINOR=3.11
FROM python:${PYTHON_MINOR}

ARG PYTHON_ENV=py311
ARG VERSION=
ARG PYTHON_WHEEL

# Put the `ENTRYPOINT` on the `$PATH`
RUN \
    apt-get update && \
    apt-get install --no-install-recommends -y gosu=1.12-1+b6 && \
    rm -rf /var/lib/apt/lists/*
COPY [ "./bin/entrypoint", "/usr/local/bin/entrypoint" ]

WORKDIR "/usr/local/src/python-project-structure/"
# Install dependencies with fixed versions in a separate layer to optimize build times
# because this step takes the most time and changes the least frequently.
COPY [ "./requirements/${PYTHON_ENV}/user.txt", "./requirements/${PYTHON_ENV}/" ]
RUN pip install --no-cache-dir -r "./requirements/${PYTHON_ENV}/user.txt"
# Install this package in the most common/standard Python way while still being able to
# build the image locally.
COPY [ "./dist/${PYTHON_WHEEL}", "./dist/" ]
# hadolint ignore=DL3013
RUN pip install --no-cache-dir "./dist/${PYTHON_WHEEL}" && \
    rm -rfv "./dist/"

# Find the same home directory even when run as another user, e.g. `root`.
ENV HOME="/home/python-project-structure"
WORKDIR "/home/python-project-structure/"
ENTRYPOINT [ "entrypoint" ]
CMD [ "python-project-structure" ]

# https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys
LABEL org.opencontainers.image.url="https://gitlab.com/rpatterson/python-project-structure"
LABEL org.opencontainers.image.documentation="https://gitlab.com/rpatterson/python-project-structure"
LABEL org.opencontainers.image.source="https://gitlab.com/rpatterson/python-project-structure"
LABEL org.opencontainers.image.title="Python Project Structure"
LABEL org.opencontainers.image.description="Python project structure foundation or template"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.authors="Ross Patterson <me@rpatterson.net>"
LABEL org.opencontainers.image.vendor="rpatterson.net"
LABEL org.opencontainers.image.base.name="docker.io/library/python:${PYTHON_MINOR}"
# Build-time `LABEL`s
LABEL org.opencontainers.image.version=${VERSION}
