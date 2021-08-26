# From https://hub.docker.com/_/python
FROM python:3

ENV PUID="1000"
ENV PGID="100"

# Install the application and dependencies
WORKDIR /usr/local/src/prunerr/
COPY [ "./", "./" ]
RUN [ "pip", "install", "--no-cache-dir", "-r", "./requirements.txt" ]

# Add a user to support matching permissions inside and outside the container
RUN adduser --uid "$PUID" --gid "$PGID" --disabled-password --gecos "Prunerr,,," \
    "prunerr"
USER $PUID:$PGID

WORKDIR /home/prunerr/
ENTRYPOINT  [ "prunerr" ]
CMD [ "daemon" ]
