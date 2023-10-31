# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Tests covering the `prunerr.runner` module.
"""

import os
import pathlib

from unittest import mock

import prunerr.runner

from .. import tests

HOME = pathlib.Path(__file__).parent / "home" / "empty"
ENV = dict(tests.PrunerrTestCase.ENV, HOME=str(HOME))


@mock.patch.dict(os.environ, ENV)
class PrunerrRunnerTests(tests.PrunerrTestCase):
    """
    Tests covering the `prunerr.runner` module.
    """

    HOME = HOME
    CONFIG = HOME / ".config" / "prunerr.yml"
    ENV = ENV

    RESPONSES_DIR = tests.PrunerrTestCase.RESPONSES_DIR.parent / "download-client-only"

    def test_runner_empty_config(self):
        """
        The runner succeeds with an empty configuration file.
        """
        runner = prunerr.runner.PrunerrRunner(self.CONFIG)
        with self.assertRaises(
            prunerr.runner.PrunerrValidationError,
            msg="Wrong empty config file validation exception type",
        ) as exc_context:
            runner.update()
        self.assertIn(
            "must include at least one URL",
            str(exc_context.exception),
            "Wrong empty config file validation error message",
        )

    def test_runner_missing_config(self):
        """
        The runner succeeds with a missing configuration file.
        """
        runner = prunerr.runner.PrunerrRunner(
            self.HOME.parent / "missing" / ".config" / "prunerr.yml",
        )
        with self.assertRaises(
            prunerr.runner.PrunerrValidationError,
            msg="Wrong missing config file validation exception type",
        ) as exc_context:
            runner.update()
        self.assertIn(
            "file not found",
            str(exc_context.exception),
            "Wrong missing config file validation error message",
        )

    def test_runner_empty_operations(self):
        """
        The runner succeeds when only a download client is defined.
        """
        runner = prunerr.runner.PrunerrRunner(
            self.HOME.parent / "download-client-only" / ".config" / "prunerr.yml",
        )
        default_request_mocks = self.mock_responses()
        runner.update()
        self.assertIsNone(
            runner.exec_(),
            "Wrong `exec` result from empty config file",
        )
        self.assert_request_mocks(default_request_mocks)
