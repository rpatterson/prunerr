## Container image for use by end users

# Stay as close to a vanilla environment as possible
FROM buildpack-deps:stable

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

# Find the same home directory even when run as another user, e.g. `root`.
ENV HOME="/home/project-structure"
WORKDIR "/home/project-structure/"
ENTRYPOINT [ "entrypoint" ]

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
# Build-time `LABEL`s
ARG VERSION=
LABEL org.opencontainers.image.version=${VERSION}
