"""
Python project structure foundation or template, command-line execution.
"""

import argparse

# Define command line options and arguments
parser = argparse.ArgumentParser(
    description=__doc__.strip(), formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)


def main(args=None):
    parser.parse_args(args=args)


main.__doc__ = __doc__


if __name__ == "__main__":  # pragma: no cover
    main()
