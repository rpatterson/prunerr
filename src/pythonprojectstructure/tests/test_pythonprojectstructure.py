"""
python-project-structure unit and integration tests.
"""

import unittest

# BBB: Python 2 compatibility
try:
    import contextlib2 as contextlib
except ImportError:  # pragma: no cover
    import contextlib

import six

import pythonprojectstructure


class PythonProjectStructureTests(unittest.TestCase):
    """
    python-project-structure unit and integration tests.
    """

    def getCliErrorMessages(self, args):
        """
        Run the CLI script and return any error messages.
        """
        stderr_file = six.StringIO()
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(stderr_file):
                pythonprojectstructure.main(args=args)
        return stderr_file.getvalue()

    def test_cli_help(self):
        """
        The command line script is self-docummenting.
        """
        stdout_file = six.StringIO()
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(stdout_file):
                pythonprojectstructure.main(args=["--help"])
        stdout = stdout_file.getvalue()
        self.assertIn(
            pythonprojectstructure.__doc__.strip(),
            stdout,
            "The console script name missing from --help output",
        )

    def test_cli_options(self):
        """
        The command line script accepts options controlling behavior.
        """
        result = pythonprojectstructure.main(args=[])
        self.assertIsNone(
            result,
            "Wrong console script options return value",
        )

    def test_cli_option_errors(self):
        """
        The command line script displays useful messages for invalid option values.
        """
        stderr = self.getCliErrorMessages(args=["--non-existent-option"])
        self.assertIn(
            "error: unrecognized arguments: --non-existent-option",
            stderr,
            "Wrong invalid option message",
        )
