"""
Tests for Prunerr.
"""

import os
import pathlib
import mimetypes
import email.utils
import urllib.parse

import unittest

import requests_mock

import prunerr


class PrunerrTestCase(unittest.TestCase):
    """
    Constants and set-up used in all Prunerr tests.
    """

    maxDiff = None

    HOME = pathlib.Path(prunerr.__path__[0]).parents[1] / "home"
    CONFIG = HOME / ".config" / "prunerr.yml"

    RESPONSES_DIR = pathlib.Path(__file__).parent / "responses" / "default"

    def setUp(self):
        """
        Set up used in all Prunerr tests.
        """
        super().setUp()

        # Mock HTTP/S requests:
        # https://requests-mock.readthedocs.io/en/latest/fixture.html#fixtures
        self.requests_mock = requests_mock.Mocker()
        self.addCleanup(self.requests_mock.stop)
        self.requests_mock.start()

    def mock_responses(self, responses_dir=RESPONSES_DIR):
        """
        Mock response responses from files in the given directory.

        The relative paths in the mock dir are un-escaped to URLs and used to create the
        response mocks for those URLs.  The benefits of this approach are:
        - Better editor experience for response bodies (e.g. JSON)
        - More readable diffs in VCS
        - Potential to be re-used outside the test suite programming language
        """
        response_mocks = {}
        for dirpath, _, filenames in os.walk(responses_dir, followlinks=True):
            for filename in filenames:
                mock_file_path = pathlib.Path(dirpath) / filename
                mock_parent_relative = mock_file_path.parent.relative_to(responses_dir)
                mock_stat = mock_file_path.stat()
                mock_bytes = mock_file_path.read_bytes()
                mock_headers = {
                    "Last-Modified": email.utils.formatdate(
                        timeval=mock_stat.st_mtime,
                        usegmt=True,
                    ),
                    "Content-Length": str(len(mock_bytes)),
                }
                mock_type, _ = mimetypes.guess_type(mock_file_path.name)
                if mock_type:
                    mock_headers["Content-Type"] = mock_type
                mock_basename_split = urllib.parse.urlsplit(
                    urllib.parse.unquote(mock_file_path.stem),
                )
                mock_url_split = urllib.parse.SplitResult(
                    scheme=mock_parent_relative.parents[-2].name,
                    netloc=mock_parent_relative.parents[-3].name,
                    path=str(
                        mock_file_path.parent.relative_to(
                            responses_dir / mock_parent_relative.parents[-3]
                        )
                        / mock_basename_split.path
                    ),
                    query=mock_basename_split.query,
                    fragment=mock_basename_split.fragment,
                )
                response_mocks[mock_url_split] = self.requests_mock.get(
                    mock_url_split.geturl(),
                    # Ensure the download response includes `Last-Modified`
                    headers=mock_headers,
                    content=mock_bytes,
                )
        return response_mocks
