## Container image for use by end users

# Stay as close to a vanilla Python environment as possible
FROM python:3

WORKDIR "/usr/local/src/python-project-structure/"
# Install dependencies with fixed versions in a separate layer to optimize build times
# because this step takes the most time and changes the least frequently.
COPY [ "./requirements.txt", "./" ]
RUN pip install --no-cache-dir -r "./requirements.txt"
# Install this package in the most common/standard Python way while still being able to
# build the image locally.
COPY [ "./", "./" ]
RUN pip install --no-cache-dir "./"

# Stay as close to the common/standard Python user run-time environment as possible.
# Match permissions inside and outside the container.  Default to the common/standard
# main/first user and group IDs
USER 1000
# Find the same home directory even when run as another user, e.g. `root`.
ENV HOME="/home/python-project-structure"
WORKDIR "/home/python-project-structure/"
ENTRYPOINT python
