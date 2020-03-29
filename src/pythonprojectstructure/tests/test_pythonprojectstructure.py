"""
python-project-structure unit and integration tests.
"""

import contextlib
import io
import unittest

import pythonprojectstructure


class PythonProjectStructureTests(unittest.TestCase):
    """
    python-project-structure unit and integration tests.
    """

    def test_cli_help(self):
        """
        The command line script is self-docummenting.
        """
        stdout_file = io.StringIO()
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(stdout_file):
                pythonprojectstructure.main(args=["python-project-structure", "--help"])
        stdout = stdout_file.getvalue()
        self.assertIn(
            pythonprojectstructure.__doc__.strip(),
            stdout,
            "The console script name missing from --help output",
        )
