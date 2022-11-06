"""
Test the python-project-structure Command-Line Interface.
"""

import sys
import io
import subprocess
import contextlib

import unittest

import pythonprojectstructure


class PythonProjectStructureCLITests(unittest.TestCase):
    """
    Test the python-project-structure Command-Line Interface.
    """

    def test_importable(self):
        """
        The Python package is on `sys.path` and thus importable.
        """
        import_process = subprocess.run(
            [sys.executable, "-c", "import pythonprojectstructure"],
            check=False,
        )
        self.assertEqual(
            import_process.returncode,
            0,
            "The Python package not importable",
        )

    def get_cli_error_messages(self, args):
        """
        Run the CLI script and return any error messages.
        """
        stderr_file = io.StringIO()
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(stderr_file):
                pythonprojectstructure.main(args=args)
        return stderr_file.getvalue()

    def test_cli_help(self):
        """
        The command line script is self-docummenting.
        """
        stdout_file = io.StringIO()
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
        result = pythonprojectstructure.main(args=["foobar"])
        self.assertIsNone(
            result,
            "Wrong console script options return value",
        )

    def test_cli_option_errors(self):
        """
        The command line script displays useful messages for invalid option values.
        """
        stderr = self.get_cli_error_messages(args=["foobar", "--non-existent-option"])
        self.assertIn(
            "error: unrecognized arguments: --non-existent-option",
            stderr,
            "Wrong invalid option message",
        )

    def test_cli_module_main(self):
        """
        The package/module supports execution via Python's `-m` option.
        """
        module_main_process = subprocess.run(
            [sys.executable, "-m", "pythonprojectstructure", "foobar"],
            check=False,
        )
        self.assertEqual(
            module_main_process.returncode,
            0,
            "Running via Python's `-m` option exited with non-zero status code",
        )
