## Capture test fixture generation and other testing maintenance tasks

### Defensive settings for make:
#     https://tech.davis-hansson.com/p/make/
SHELL:=bash
.ONESHELL:
.SHELLFLAGS:=-xeu -o pipefail -c
.SILENT:
.DELETE_ON_ERROR:
MAKEFLAGS+=--warn-undefined-variables
MAKEFLAGS+=--no-builtin-rules
PS1?=$$


## Top-level targets

.PHONY: all
### Default target
all: build

.PHONY: build
### Perform any currently necessary local set-up common to most operations
build: ./example-5s.mkv


## Real targets

## Generate a basic video file for tests.
# The most common example that doesn't use a bunch of disk space that should pass muster
# via any `$ ffprobe ...` check except maybe runtime.
./example-5s.mkv:
# https://twitter.com/ffmpeg/status/1184173404636598272?lang=en
	ffmpeg -f lavfi -i "testsrc=d=5:s=1920x1080:r=24,format=yuv420p" -f "lavfi" \
	    -i "sine=f=440:b=4" -shortest -c:v "libx265" "$(@)"
