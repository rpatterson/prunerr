# From https://hub.docker.com/_/python
FROM python:3

# Add a user whose home directory will contain the configuration file
ARG PUID=1000
ARG PGID=100
ARG REQUIREMENTS=./requirements.txt

# Add a user whose home directory will contain the configuration file
RUN adduser --uid "${PUID}" --gid "${PGID}" --disabled-password \
    --gecos "Python Project Structure,,," "python-project-structure"

# Install the application and dependencies
WORKDIR /usr/local/src/python-project-structure/
COPY [ "./${REQUIREMENTS}", "./${REQUIREMENTS}" ]
RUN pip install --no-cache-dir -r "${REQUIREMENTS}"
COPY [ "./", "./" ]
RUN pip install --no-cache-dir -e "./"

USER $PUID:$PGID
WORKDIR /home/python-project-structure/
