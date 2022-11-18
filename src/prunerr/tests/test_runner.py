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

    RESPONSES_DIR = tests.PrunerrTestCase.RESPONSES_DIR.parent / "default"

    def test_runner_empty_config(self):
        """
        The runner succeeds with a configuration file as close to empty as supported.
        """
        runner = prunerr.runner.PrunerrRunner(self.CONFIG)
        runner.update()
        self.assertIsNone(
            runner.exec_(),
            "Wrong `exec` result from empty config file",
        )
