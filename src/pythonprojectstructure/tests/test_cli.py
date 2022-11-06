"""
Test the python-project-structure Command-Line Interface.
"""

import sys
import io
import subprocess
import contextlib
import pathlib

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

    def test_cli_subcommand(self):
        """
        The command line supports sub-commands.
        """
        self.assertIsNone(
            pythonprojectstructure.main(args=["foobar"]),
            "Wrong console script sub-command return value",
        )

    def test_cli_options(self):
        """
        The command line script accepts options controlling behavior.
        """
        self.assertIsNone(
            pythonprojectstructure.main(args=["foobar", "-q"]),
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

    def test_cli_exit_code(self):
        """
        The command line script exits with status code zero if there are no exceptions.
        """
        # Find the location of the `console_scripts` for this test environment
        prefix_path = pathlib.Path(sys.argv[0]).parent
        while not (prefix_path / "bin").is_dir():
            prefix_path = prefix_path.parent
            if prefix_path.parent is prefix_path.parents[-1]:  # pragma: no cover
                raise ValueError(f"Could not find script prefix path: {sys.argv[0]}")

        script_process = subprocess.run(
            [prefix_path / "bin" / "python-project-structure", "foobar"],
            check=False,
        )
        self.assertEqual(
            script_process.returncode,
            0,
            "Running the console script exited with non-zero status code",
        )
