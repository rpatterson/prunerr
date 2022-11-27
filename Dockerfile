## Container image for use by end users

# Stay as close to a vanilla Python environment as possible
FROM python:3

# Put the `ENTRYPOINT` on the `$PATH`
RUN apt-get update && apt-get install -y gosu && rm -rf /var/lib/apt/lists/*
COPY [ "./bin/entrypoint", "/usr/local/bin/entrypoint" ]

WORKDIR "/usr/local/src/python-project-structure/"
# Install dependencies with fixed versions in a separate layer to optimize build times
# because this step takes the most time and changes the least frequently.
COPY [ "./requirements.txt", "./" ]
RUN pip install --no-cache-dir -r "./requirements.txt"
# Install this package in the most common/standard Python way while still being able to
# build the image locally.
RUN --mount=source=./,target=./,rw,type=bind pip install --no-cache-dir "./"

# Find the same home directory even when run as another user, e.g. `root`.
ENV HOME="/home/python-project-structure"
WORKDIR "/home/python-project-structure/"
ENTRYPOINT [ "entrypoint" ]
CMD [ "python-project-structure" ]
