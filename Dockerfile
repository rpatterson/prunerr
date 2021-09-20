# From https://hub.docker.com/r/lsiobase/alpine
# Used to get `PUID`/`PGID` support
FROM lsiobase/alpine:3.14

# Install the application and dependencies
WORKDIR /usr/local/src/prunerr/
COPY [ "./", "./" ]
# TODO: Use build stages to minimize image size
RUN [ \
    "apk", "add", "--no-cache", "python3", "py3-pip", "gcc", "musl-dev", "python3-dev" \
]
RUN [ "pip3", "install", "--no-cache-dir", "-r", "./requirements.txt" ]
RUN [ "apk", "del", "--no-cache", "gcc", "musl-dev", "python3-dev" ]

# Add the S6-overlay service
WORKDIR /
COPY [ "./root/", "./" ]
