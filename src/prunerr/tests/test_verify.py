"""
Prunerr verifies corrupt items and resumes them once verified.
"""

import os

from unittest import mock

import prunerr.downloadclient

from .. import tests


@mock.patch.dict(os.environ, tests.PrunerrTestCase.ENV)
class PrunerrVerifyTests(tests.PrunerrTestCase):
    """
    Prunerr verifies corrupt items and resumes them once verified.
    """

    RESPONSES_DIR = tests.PrunerrTestCase.RESPONSES_DIR.parent / "verify"

    def test_verify_workflow(self):
        """
        Prunerr verifies corrupt items and resumes them once verified.
        """
        verify_request_mocks = self.mock_responses()
        prunerr.main(args=[f"--config={self.CONFIG}", "verify"])
        # All the effects of the `verify` sub-command take place in the download client
        # RPC requests and responses, so all the assertions are covered below
        self.assert_request_mocks(verify_request_mocks)

    def test_verify_exec(self):
        """
        Prunerr verifies corrupt items as a part of the `exec` sub-command.
        """
        verify_request_mocks = self.mock_responses()
        prunerr.main(args=[f"--config={self.CONFIG}", "exec"])
        self.assert_request_mocks(verify_request_mocks)
