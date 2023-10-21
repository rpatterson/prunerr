#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
#
# SPDX-License-Identifier: MIT

"""
Map file formats unknown by Vale to a similar format is does know.
"""

import sys
import re
import contextlib
import pathlib
import argparse

import configobj

FORMATS_GLOB_RE = re.compile(r"^\*\.\{(?P<suffixes>[A-Za-z0-9,]+)\}$")

arg_parser = argparse.ArgumentParser(
    description=__doc__.strip(),
)
arg_parser.add_argument(
    "--format",
    "-f",
    default="pl",
    help="Map unknown formats to this format. (default: `pl`)",
)
arg_parser.add_argument(
    "--files",
    "-l",
    type=argparse.FileType(),
    default=sys.stdin,
    help=(
        "A file listing file paths one per line, such as from `$ git ls-files`. "
        "Check the extensions of these paths for unknown formats. (default: `stdin`)"
    ),
)
arg_parser.add_argument(
    "output",
    type=argparse.FileType(),
    help="Map unknown formats in this Vale configuration file.",
)
arg_parser.add_argument(
    "configs",
    type=argparse.FileType(),
    nargs="*",
    help="Get known formats from the `output` file and these Vale configuration files.",
)


def iter_pattern_suffixes(config):
    """
    Get the matching suffixes from a Vale configuration's format patterns.
    """
    for format_pattern in config.sections:
        format_settings = config[format_pattern]
        if not format_settings.get("BasedOnStyles", "").strip():
            # Not a section defining per-format settings:
            continue
        yield (
            format_pattern,
            FORMATS_GLOB_RE.match(format_pattern).group("suffixes").split(","),
        )


def main(args=None):  # pylint: disable=missing-function-docstring
    parsed_args = arg_parser.parse_args(args=args)

    # Parse the Vale configurations:
    with contextlib.closing(parsed_args.output):
        output = configobj.ConfigObj(parsed_args.output, list_values=False)
    configs = [output]
    for config_file in parsed_args.configs:
        with contextlib.closing(config_file):
            configs.append(configobj.ConfigObj(config_file, list_values=False))

    # Collect all the formats in configured format patterns sections and consider those
    # to be the already known formats:
    known_formats = set()
    output_format_patterns = list(iter_pattern_suffixes(output))
    for _, suffixes in output_format_patterns:
        known_formats.update(suffixes)
    for config in configs:
        for _, suffixes in iter_pattern_suffixes(config):
            known_formats.update(suffixes)

    # Find the formats for which there is no currently configured format pattern:
    with contextlib.closing(parsed_args.files):
        file_formats = {
            pathlib.Path(file_path[:-1]).suffix[1:]
            for file_path in parsed_args.files
            if pathlib.Path(file_path).suffix
        }
    unknown_formats = file_formats - known_formats

    # Add unknown formats to the pattern, adding a mapping if needed:
    format_pattern, suffixes = output_format_patterns[0]
    for unknown_format in unknown_formats:
        if unknown_format not in output["formats"]:
            output["formats"][unknown_format] = parsed_args.format
        suffixes.append(unknown_format)
    output.rename(format_pattern, "*.{" + ",".join(suffixes) + "}")
    # Write the changed configuration back to it's file:
    with open(parsed_args.output.name, "wb") as output_opened:
        output.write(output_opened)
    sys.exit()


main.__doc__ = __doc__


if __name__ == "__main__":
    main()
