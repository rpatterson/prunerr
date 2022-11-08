"""
Tests for Prunerr.
"""

import re
import pathlib
import mimetypes
import email.utils
import urllib.parse
import json

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

    # From /usr/lib/python3.10/wsgiref/validate.py:340
    HTTP_METHODS = ("GET", "HEAD", "POST", "OPTIONS", "PATCH", "PUT", "DELETE", "TRACE")
    HTTP_METHODS_RE = re.compile(f"^({'|'.join(HTTP_METHODS)})")
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

    def mock_responses(
        self,
        responses_dir=RESPONSES_DIR,
    ):  # pylint: disable=too-many-locals
        """
        Mock response responses from files in the given directory.

        The relative paths in the mock dir are un-escaped to URLs and used to create the
        response mocks for those URLs.  The benefits of this approach are:
        - Better editor experience for response bodies (e.g. JSON)
        - More readable diffs in VCS
        - Potential to be re-used outside the test suite programming language
        """
        response_mocks = {}
        for request_headers_path in responses_dir.glob("**/request-headers.json"):
            method = self.HTTP_METHODS_RE.match(request_headers_path.parent.name).group(
                1
            )
            url_unquoted_path = pathlib.PurePosixPath(
                urllib.parse.unquote(
                    str(
                        request_headers_path.parents[1].relative_to(responses_dir),
                    ),
                ),
            )
            url_path_split = urllib.parse.urlsplit(
                str(url_unquoted_path.relative_to(url_unquoted_path.parents[-3])),
            )
            url_split = urllib.parse.SplitResult(
                scheme=url_unquoted_path.parents[-2].name,  # pylint: disable=no-member
                netloc=url_unquoted_path.parents[-3].name,  # pylint: disable=no-member
                path=url_path_split.path,
                query=url_path_split.query,
                fragment=url_path_split.fragment,
            )

            responses = []
            for response_path in request_headers_path.parent.glob("*/response.*"):
                if response_path.name.endswith("~"):
                    # Ignore backup files
                    continue
                response_headers = {}
                response_headers_path = response_path.parent / "response-headers.json"
                if response_headers_path.exists():
                    response_headers = json.load(response_headers_path)
                response_stat = response_path.stat()
                response_bytes = response_path.read_bytes()

                if "Last-Modified" not in response_headers:
                    response_headers["Last-Modified"] = email.utils.formatdate(
                        timeval=response_stat.st_mtime,
                        usegmt=True,
                    )
                if "Content-Length" not in response_headers:
                    response_headers["Content-Length"] = str(len(response_bytes))
                if "Content-Type" not in response_headers:
                    response_type, _ = mimetypes.guess_type(response_path.name)
                    if response_type:
                        response_headers["Content-Type"] = response_type

                responses.append(
                    dict(headers=response_headers, content=response_bytes),
                )

            with request_headers_path.open() as request_headers_opened:
                request_headers = json.load(request_headers_opened)
            response_mocks[url_split] = self.requests_mock.register_uri(
                method=method,
                url=url_split.geturl(),
                request_headers=request_headers,
                response_list=responses,
            )
        return response_mocks
