"""
python-project-structure unit and integration tests.
"""

import sys
import subprocess

import unittest


class PythonProjectStructureTests(unittest.TestCase):
    """
    python-project-structure unit and integration tests.
    """

    def test_importable(self):
        """
        The Python package is on `sys.path` and thus importable.
        """
        import_process = subprocess.run(
            [sys.executable, "-c", "import pythonprojectstructure"],
            check=True,
        )
        self.assertEqual(
            import_process.returncode,
            0,
            "The Python package not importable",
        )
