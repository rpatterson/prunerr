"""
Tests for Prunerr.
"""

import re
import pathlib
import mimetypes
import email.utils
import email.message
import urllib.parse
import json
import tempfile
import unittest

import yaml
import requests_mock

import prunerr


def parse_content_type(content_type):
    """
    Parse an RFC822-style `Content-Type` header.

    Useful to safely extract the MIME type from the charset.
    """
    message = email.message.Message()
    message["Content-Type"] = content_type
    major_type, minor_type = message.get_params()[0][0].split("/")
    return major_type, minor_type


class PrunerrTestCase(
    unittest.TestCase
):  # pylint: disable=too-many-instance-attributes
    """
    Constants and set-up used in all Prunerr tests.
    """

    maxDiff = None

    HOME = pathlib.Path(prunerr.__path__[0]).parents[1] / "home"
    CONFIG = HOME / ".config" / "prunerr.yml"
    ENV = {
        "HOME": str(HOME),
        "DEBUG": "true",
    }

    STORAGE_DIR = pathlib.PurePath("media", "Library")
    INCOMPLETE_DIR = STORAGE_DIR / "incomplete"
    DOWNLOADS_DIR = STORAGE_DIR / "downloads"
    SONARR_DOWNLOADS_DIR = DOWNLOADS_DIR / "Sonarr" / "Videos" / "Series"
    RADARR_DOWNLOADS_DIR = DOWNLOADS_DIR / "Radarr" / "Videos" / "Movies"
    SEEDING_DIR = STORAGE_DIR / "seeding"
    SONARR_SEEDING_DIR = SEEDING_DIR / "Sonarr" / "Videos" / "Series"
    RADARR_SEEDING_DIR = SEEDING_DIR / "Radarr" / "Videos" / "Movies"

    # From /usr/lib/python3.10/wsgiref/validate.py:340
    HTTP_METHODS = ("GET", "HEAD", "POST", "OPTIONS", "PATCH", "PUT", "DELETE", "TRACE")
    HTTP_METHODS_RE = re.compile(f"^({'|'.join(HTTP_METHODS)})")
    RESPONSES_DIR = pathlib.Path(__file__).parent / "responses" / "default"

    def setUp(self):
        """
        Set up used in all Prunerr tests.
        """
        super().setUp()

        # Convenient access to the parsed configuration file
        with self.CONFIG.open() as config_opened:
            self.config = yaml.safe_load(config_opened)
        # Convenient access to parsed mocked API/RPC request responses
        self.servarr_download_client_responses = {}
        self.servarr_urls = [
            servarr_config["url"] for servarr_config in self.config["servarrs"].values()
        ]
        for servarr_url in self.servarr_urls:
            servarr_url = urllib.parse.urlsplit(servarr_url)
            with (
                self.RESPONSES_DIR
                / servarr_url.scheme
                / urllib.parse.quote(servarr_url.netloc)
                / "api"
                / "v3"
                / "downloadclient%3Fapikey%3D"
                / "GET"
                / "0-response"
                / "response.json"
            ).open() as servarr_download_client_response:
                self.servarr_download_client_responses[
                    servarr_url.geturl()
                ] = json.load(servarr_download_client_response)

        # Mock HTTP/S requests:
        # https://requests-mock.readthedocs.io/en/latest/fixture.html#fixtures
        self.requests_mock = requests_mock.Mocker()
        self.addCleanup(self.requests_mock.stop)
        self.requests_mock.start()

        # Create a temporary directory for mutable test data
        self.tmp_dir = (
            tempfile.TemporaryDirectory(  # pylint: disable=consider-using-with
                prefix=f"{self.__class__.__module__}-",
                suffix=".d",
            )
        )
        self.addCleanup(self.tmp_dir.cleanup)
        self.tmp_path = pathlib.Path(self.tmp_dir.name)

        # Convenience access to frequently used paths
        self.storage_dir = self.tmp_path / self.STORAGE_DIR
        self.incomplete_dir = self.tmp_path / self.INCOMPLETE_DIR
        self.downloads_dir = self.tmp_path / self.DOWNLOADS_DIR
        self.sonarr_downloads_dir = self.tmp_path / self.SONARR_DOWNLOADS_DIR
        self.radarr_downloads_dir = self.tmp_path / self.RADARR_DOWNLOADS_DIR
        self.seeding_dir = self.tmp_path / self.SEEDING_DIR
        self.sonarr_seeding_dir = self.tmp_path / self.SONARR_SEEDING_DIR
        self.radarr_seeding_dir = self.tmp_path / self.RADARR_SEEDING_DIR

    def patch_paths(self, data):
        """
        Adjust Servarr/transmission storage paths for testing.
        """
        is_list = True
        if not isinstance(data, list):
            is_list = False
            data = [data]
        for item in data:
            if not isinstance(item, dict):
                continue
            for key, value in list(item.items()):
                if isinstance(value, (str)) and value.startswith("/media/"):
                    # Keys containing storage paths in this object
                    item[key] = f"{self.tmp_path}{value}"
                    pathlib.Path(item[key]).parent.mkdir(parents=True, exist_ok=True)
                elif isinstance(value, (dict, list)):
                    # Keys containing objects that may themselves contain storage paths
                    self.patch_paths(item[key])
        if not is_list:
            (data,) = data
        return data

    def mock_responses(
        self,
        responses_dir=None,
    ):  # pylint: disable=too-many-locals
        """
        Mock response responses from files in the given directory.

        The relative paths in the mock dir are un-escaped to URLs and used to create the
        response mocks for those URLs.  The benefits of this approach are:
        - Better editor experience for response bodies (e.g. JSON)
        - More readable diffs in VCS
        - Potential to be re-used outside the test suite programming language
        """
        if responses_dir is None:
            responses_dir = self.RESPONSES_DIR
        request_mocks = []
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
            for response_path in sorted(
                request_headers_path.parent.glob("*/response.*"),
            ):
                if response_path.name.endswith("~"):
                    # Ignore backup files
                    continue
                response_headers = {}
                response_headers_path = response_path.parent / "response-headers.json"
                if response_headers_path.exists():
                    with response_headers_path.open() as response_headers_opened:
                        response_headers = json.load(response_headers_opened)
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

                # Patch transmission/Servarr storage paths if the body is JSON
                if "Content-Type" in response_headers:
                    _, minor_type = parse_content_type(response_headers["Content-Type"])
                    if minor_type.lower() == "json":
                        response_bytes = json.dumps(
                            self.patch_paths(json.loads(response_bytes))
                        ).encode()

                responses.append(
                    dict(headers=response_headers, content=response_bytes),
                )

            with request_headers_path.open() as request_headers_opened:
                request_headers = json.load(request_headers_opened)
            request_mocks.append(
                (
                    self.requests_mock.register_uri(
                        method=method,
                        url=url_split.geturl(),
                        complete_qs=True,
                        request_headers=request_headers,
                        response_list=responses,
                    ),
                    responses,
                )
            )
        return request_mocks

    def assert_request_mocks(self, request_mocks):
        """
        Assert that all request mocks have been called and each only once.
        """
        for request_mock, mock_responses in request_mocks:
            if request_mock.call_count < len(mock_responses):
                response_contents = []
                for response_params in mock_responses:
                    response_content = response_params.get(
                        "json",
                        response_params.get("text", response_params.get("content")),
                    )
                    if isinstance(
                        response_content, (str, bytes)
                    ) and "Content-Type" in response_params.get("headers", {}):
                        _, minor_type = parse_content_type(
                            response_params["headers"]["Content-Type"],
                        )
                        if minor_type.lower() == "json":
                            response_content = json.loads(response_content)
                    response_contents.append(response_content)
                self.assertEqual(
                    response_contents,
                    response_contents[: request_mock.call_count],
                    "Some response mocks not called: "
                    f"{request_mock._method} "  # pylint: disable=protected-access
                    f"{request_mock._url}",  # pylint: disable=protected-access
                )
            elif request_mock.call_count > len(mock_responses):
                request_contents = []
                for mock_call in request_mock.request_history:
                    request_content = mock_call.text
                    if "Accept" in mock_call.headers:
                        _, minor_type = parse_content_type(mock_call.headers["Accept"])
                        if minor_type.lower() == "json":
                            request_content = mock_call.json()
                    request_contents.append(request_content)
                self.assertEqual(
                    request_contents[: len(mock_responses)],
                    request_contents,
                    "More requests than mocks: "
                    f"{request_mock._method} "  # pylint: disable=protected-access
                    f"{request_mock._url}",  # pylint: disable=protected-access
                )
