# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Test the prunerr Command-Line Interface.
"""

import sys
import os
import collections
import io
import runpy
import subprocess  # nosec B404
import contextlib
import pathlib
import logging

from unittest import mock

import prunerrtests

import prunerr


@mock.patch.dict(os.environ, prunerrtests.PrunerrTestCase.ENV)
class PrunerrCLITests(prunerrtests.PrunerrTestCase):
    """
    Test the prunerr command-line interface.
    """

    LOGGERS = [
        logging.getLogger(),
        logging.getLogger(prunerr.__name__),
        logging.getLogger(prunerr.runner.__name__),
        logging.getLogger(prunerr.downloadclient.__name__),
        logging.getLogger(prunerr.downloaditem.__name__),
        logging.getLogger(prunerr.operations.__name__),
        logging.getLogger(prunerr.servarr.__name__),
    ]
    LOGGER_ATTRS = ["handlers", "level", "filters"]

    def setUp(self):
        """
        Capture what's needed to restore logging after calling ``main()``.

        The logging configuration is global state which breaks isolation between
        tests. So any tests which call ``config_cli_logging()``, which ``main()`` calls,
        need to restore the logging configuration back to what it was before
        ``prunerr.config_cli_logging()`` made it's changes.
        """
        super().setUp()

        def cleanup_logging(
            loggers_state: list = [
                {attr: getattr(unconfigured_logger, attr) for attr in self.LOGGER_ATTRS}
                for unconfigured_logger in self.LOGGERS
            ],
        ):
            """
            Restore the logging configuration and caches from before calling ``main()``.

            :param loggers_state: The state of the loggers to be conigured from before
                running this test.
            """
            for logger_idx, configured_logger in enumerate(self.LOGGERS):
                vars(configured_logger).update(loggers_state[logger_idx])

        self.addCleanup(cleanup_logging)
        for unconfigured_logger in self.LOGGERS:
            for attr in self.LOGGER_ATTRS:
                value = getattr(unconfigured_logger, attr)
                if not isinstance(value, collections.abc.Hashable):
                    setattr(unconfigured_logger, attr, type(value)())

    def test_importable(self):
        """
        The Python package is on `sys.path` and importable.
        """
        import_process = subprocess.run(  # nosec B603
            [sys.executable, "-c", "import prunerr"],
            check=False,
        )
        self.assertEqual(
            import_process.returncode,
            0,
            "The Python package not importable",
        )

    def get_cli_error_messages(self, args: list) -> str:
        """
        Run the command-line script and return any error messages.

        :param args: Command-line arguments
        :return: Output of stderr
        """
        stderr_file = io.StringIO()
        with self.assertRaises(SystemExit, msg="Command-line didn't exit"):
            with contextlib.redirect_stderr(stderr_file):
                prunerr.main(args=args)
        return stderr_file.getvalue()

    def test_cli_help(self):
        """
        The command line script documents itself.
        """
        stdout_file = io.StringIO()
        with self.assertRaises(SystemExit, msg="Command-line didn't exit"):
            with contextlib.redirect_stdout(stdout_file):
                prunerr.main(args=["--help"])
        stdout = stdout_file.getvalue()
        self.assertIn(
            prunerr.__doc__.strip(),
            stdout.replace("\n", " "),
            "The console script name missing from --help output",
        )

    def test_cli_subcommand(self):
        """
        The command line supports sub-commands.
        """
        request_mocks = self.mock_responses()
        self.assertIsNone(
            prunerr.main(args=[f"--config={self.CONFIG}", "apply"]),
            "Wrong console script sub-command return value",
        )
        self.assert_request_mocks(request_mocks)

    def test_cli_options(self):
        """
        The command line script accepts options controlling behavior.
        """
        request_mocks = self.mock_responses()
        self.assertIsNone(
            prunerr.main(
                args=["--log-level", "DEBUG", f"--config={self.CONFIG}", "apply"],
            ),
            "Wrong console script options return value",
        )
        self.assert_request_mocks(request_mocks)

    def test_cli_option_errors(self):
        """
        The command line script displays useful messages for invalid option values.
        """
        stderr = self.get_cli_error_messages(
            args=[
                f"--config={self.CONFIG}",
                "apply",
                "--non-existent-option",
            ]
        )
        self.assertIn(
            "error: unrecognized arguments: --non-existent-option",
            stderr,
            "Wrong invalid option message",
        )

    def test_cli_dash_m_option(self):
        """
        The package supports running by using Python's `-m` command-line option.
        """
        module_main_process = subprocess.run(  # nosec B603
            [sys.executable, "-m", "prunerr", "apply", "--help"],
            check=False,
        )
        self.assertEqual(
            module_main_process.returncode,
            0,
            "Running via Python's `-m` option exited with non-zero status code",
        )

    def test_cli_module_main(self):
        """
        The package exits with the right exception from the command-line.
        """
        with self.assertRaises(
            SystemExit,
            msg="Command-line didn't exit",
        ) as exc_context:
            runpy.run_module("prunerr")
        self.assertEqual(
            exc_context.exception.code,
            2,
            "Wrong `runpy` exit status code",
        )

    def test_cli_exit_code(self):
        """
        The command line script exits with status code zero if it raises no exceptions.

        :raises ValueError: Couldn't find script prefix path
        """
        # Find the location of the `console_scripts` for this test environment
        for parent_path in pathlib.Path(sys.argv[0]).parents:
            if (parent_path / "bin").is_dir():
                prefix_path = parent_path
                break
        else:  # pragma: no cover
            raise ValueError(f"Couldn't find script prefix path: {sys.argv[0]}")

        script_process = subprocess.run(  # nosec B603
            [prefix_path / "bin" / "prunerr", "apply", "--help"],
            check=False,
        )
        self.assertEqual(
            script_process.returncode,
            0,
            "Running the console script exited with non-zero status code",
        )

    def test_cli_empty_results(self):
        """
        Print nothing to ``stdout`` when the sub-command returns no results.
        """
        self.mock_responses()
        stdout_file = io.StringIO()
        with contextlib.redirect_stdout(stdout_file):
            prunerr.main(args=[f"--config={self.CONFIG}", "apply", "--stage=all"])
        self.assertEqual(
            stdout_file.getvalue(),
            "",
            "Verify sub-command with empty results printed something to ``stdout``",
        )
