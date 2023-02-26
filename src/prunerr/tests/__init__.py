"""
Tests for Prunerr.
"""

import sys
import os
import functools
import re
import subprocess  # nosec B404
import mimetypes
import email.utils
import email.message
import urllib.parse
import json
import tempfile
import shutil
import unittest

import yaml
import requests_mock

import prunerr
from ..utils import pathlib


def parse_content_type(content_type):  # pragma: no cover
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

    maxDiff = None  # noqa: F841

    # HTTP methods taken from /usr/lib/python3.10/wsgiref/validate.py:340
    HTTP_METHODS_RE = re.compile("^(GET|HEAD|POST|OPTIONS|PATCH|PUT|DELETE|TRACE)")

    CONFIG = prunerr.runner.PrunerrRunner.EXAMPLE_CONFIG
    HOME = CONFIG.parents[1]
    ENV = {
        "HOME": str(HOME),
        "DEBUG": "true",
    }

    # The set of request responses to mock
    RESPONSES_DIR = pathlib.Path(__file__).parent / "responses" / "default"
    DOWNLOAD_CLIENT_URL = "http://transmission:secret@localhost:9091/transmission/"

    # Download client path elements
    STORAGE_RELATIVE = pathlib.PurePath("media", "Library")
    INCOMPLETE_DIR_BASENAME = "incomplete"
    DOWNLOADED_DIR_BASENAME = "downloads"
    EXAMPLE_VIDEO = pathlib.Path(__file__).parent / "example-5s.mkv"

    # Servarr path elements
    SERVARR_TYPE = "sonarr"
    SERVARR_STORAGE_RELATIVE = pathlib.PurePath("Videos", "Series")
    SERVARR_IMPORT_PARENT_BASENAME = "Season 01"
    SERVARR_DIR_TITLE = "Foo Series (1970) [tvdbid-1]"

    def setUp(self):
        """
        Set up used in all Prunerr tests.

        Includes asssembling paths and other test fixture values that are derived from
        class attributes to allow sub-classes to use the same convenience attributes but
        modulated by the class attributes they override.
        """
        super().setUp()

        # Create a temporary directory for mutable test data
        self.tmp_dir = (
            tempfile.TemporaryDirectory(  # pylint: disable=consider-using-with
                prefix=f"{self.__class__.__module__}-",
                suffix=".d",
            )
        )
        self.addCleanup(self.tmp_dir.cleanup)
        self.tmp_path = pathlib.Path(self.tmp_dir.name)

        # Download client paths
        self.storage_dir = self.tmp_path / self.STORAGE_RELATIVE
        self.incomplete_dir = self.storage_dir / self.INCOMPLETE_DIR_BASENAME
        self.downloaded_dir = self.storage_dir / self.DOWNLOADED_DIR_BASENAME
        self.seeding_dir = (
            self.storage_dir
            / prunerr.downloadclient.PrunerrDownloadClient.SEEDING_DIR_BASENAME
        )

        # Convenient access to the parsed configuration file
        with self.CONFIG.open(encoding="utf-8") as config_opened:
            self.config = yaml.safe_load(config_opened)
        if "download-clients" in self.config:
            self.min_free_space = prunerr.downloadclient.calc_free_space_margin(
                self.config,
            )
        # Convenient access to parsed mocked API/RPC request responses
        self.servarr_download_client_responses = {}
        self.servarr_urls = []
        if "servarrs" in self.config:
            self.servarr_urls = [
                servarr_config["url"]
                for servarr_config in self.config["servarrs"].values()
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
                self.servarr_download_client_responses[servarr_url.geturl()] = [
                    prunerr.servarr.deserialize_servarr_download_client(
                        download_client_config,
                    )
                    for download_client_config in json.load(
                        servarr_download_client_response,
                    )
                ]
        self.download_client_items_responses = {}
        self.download_client_urls = set()
        for (
            servarr_download_client_response
        ) in self.servarr_download_client_responses.values():
            self.download_client_urls.update(
                download_client_config["url"]
                for download_client_config in servarr_download_client_response
                if download_client_config["enable"]
            )
        self.download_client_urls = list(self.download_client_urls)
        for download_client_url in self.download_client_urls:
            self.set_up_download_item_files(download_client_url)

        # Mock HTTP/S requests:
        # https://requests-mock.readthedocs.io/en/latest/fixture.html#fixtures
        self.requests_mock = requests_mock.Mocker()
        self.addCleanup(self.requests_mock.stop)
        self.requests_mock.start()

        # Servarr paths
        self.servarr_downloaded_dir = (
            self.downloaded_dir
            / self.SERVARR_TYPE.capitalize()
            / self.SERVARR_STORAGE_RELATIVE
        )
        self.servarr_seeding_dir = (
            self.seeding_dir
            / self.SERVARR_TYPE.capitalize()
            / self.SERVARR_STORAGE_RELATIVE
        )
        self.servarr_import_dir = (
            self.storage_dir / self.SERVARR_STORAGE_RELATIVE / self.SERVARR_DIR_TITLE
        )

        if self.download_client_urls:
            self.set_up_download_item(
                self.download_client_items_responses[self.DOWNLOAD_CLIENT_URL][
                    "arguments"
                ]["torrents"][-1]["name"]
            )

    def set_up_download_item(self, download_item_title):
        """
        Set up a download item and convenience attributes for testing against.
        """
        # Mock the common case downloading item
        self.download_item_title = download_item_title
        self.incomplete_item = self.incomplete_dir / self.download_item_title
        self.incomplete_item_file = (
            self.incomplete_item / f"{self.download_item_title}.mkv"
        )
        self.downloaded_item = self.servarr_downloaded_dir / self.download_item_title
        self.downloaded_item_file = (
            self.downloaded_item / self.incomplete_item_file.name
        )
        self.seeding_item = self.servarr_seeding_dir / self.download_item_title
        self.seeding_item_file = self.seeding_item / self.incomplete_item_file.name
        self.imported_item_file = (
            self.servarr_import_dir
            / self.SERVARR_IMPORT_PARENT_BASENAME
            / self.incomplete_item_file.name
        )

    def set_up_download_item_files(self, download_client_url):
        """
        Copy example files into place to represent download item files.
        """
        download_client_url = urllib.parse.urlsplit(download_client_url)
        if not download_client_url.port:
            return
        torrent_list_mocks = sorted(
            (
                self.RESPONSES_DIR
                / download_client_url.scheme
                / urllib.parse.quote(download_client_url.netloc)
                / urllib.parse.quote(download_client_url.path.lstrip(os.path.sep))
                / "rpc"
                / "POST"
            ).glob("*-torrent-get")
        )
        with (
            torrent_list_mocks[0] / "response.json"
        ).open() as download_client_items_response:
            self.download_client_items_responses[
                download_client_url.geturl()
            ] = json.load(download_client_items_response)
            for download_item in self.download_client_items_responses[
                download_client_url.geturl()
            ]["arguments"]["torrents"]:
                if download_item["status"] == 6:
                    download_item_dir = self.tmp_path / download_item[
                        "downloadDir"
                    ].lstrip(os.path.sep)
                else:
                    download_item_dir = self.incomplete_dir
                download_item_file = (
                    download_item_dir / download_item["files"][0]["name"]
                )
                download_item_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.EXAMPLE_VIDEO, download_item_file)

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
                elif isinstance(value, (dict, list)):
                    # Keys containing objects that may themselves contain storage paths
                    self.patch_paths(item[key])
        if not is_list:
            (data,) = data
        return data

    def mock_response_callback(
        self,
        response_mock,
        request,
        context,
    ):
        """
        Assert that the request is as expected before mocking a response to a request.
        """
        if request.text:
            self.assertEqual(
                response_mock["request"]["json"],
                request.json(),
                f"Wrong request body for {response_mock['response_dir']}",
            )
        if callable(response_mock.get("json")):
            return response_mock["json"](
                request=request,
                context=context,
                response_mock=response_mock,
            )
        return response_mock.get("json")

    def mock_responses(
        self,
        responses_dir=None,
        manual_mocks=None,
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
        self.assertTrue(
            responses_dir.is_dir(),
            f"Mock requests responses directory is not a directory: {responses_dir}",
        )
        if manual_mocks is None:
            manual_mocks = {}
        # Clear any previous mocks to support multiple groups of request mocks per test,
        self.requests_mock.stop()
        self.requests_mock = requests_mock.Mocker()
        self.addCleanup(self.requests_mock.stop)
        self.requests_mock.start()
        # Mock requests in the directory
        request_mocks = {}
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
                scheme=url_unquoted_path.parents[-2].name,
                netloc=url_unquoted_path.parents[-3].name,
                path=url_path_split.path,
                query=url_path_split.query,
                fragment=url_path_split.fragment,
            )

            responses = {}
            for response_path in sorted(
                request_headers_path.parent.glob("*/response.json"),
            ):
                if response_path.name.endswith("~"):  # pragma: no cover
                    # Ignore backup files
                    continue
                response_mock = {
                    "response_dir": response_path.parent.relative_to(
                        pathlib.Path().resolve(),
                    ),
                    "headers": {},
                }

                # Assemble headers from the file metadata
                response_stat = response_path.stat()
                response_mock["headers"]["Last-Modified"] = email.utils.formatdate(
                    timeval=response_stat.st_mtime,
                    usegmt=True,
                )
                response_mock["headers"]["Content-Type"] = mimetypes.guess_type(
                    response_path.name
                )[0]

                # Optionally read the expected response JSON from a sibling file
                response_mock["request"] = {"json": {}}
                request_json_path = response_path.parent / "request.json"
                if request_json_path.exists():
                    with request_json_path.open() as request_json_opened:
                        response_mock["request"]["json"] = self.patch_paths(
                            json.load(request_json_opened),
                        )

                # Patch transmission/Servarr storage paths if the body is JSON
                response_text = response_path.read_text().strip()
                if response_text:
                    response_mock["json"] = self.patch_paths(json.loads(response_text))

                responses[response_path.parent.name] = response_mock

            # Insert any manual mocks in the right order.  Useful for dynamic callback
            # mocks such as requesting the download client to move download items.
            for mock_order, mock_kwargs in (
                manual_mocks.get(url_split.geturl(), {})
                .get(
                    method,
                    {},
                )
                .items()
            ):
                mock_kwargs["from_mock_dir"] = responses[mock_order]
                responses[mock_order] = dict(
                    responses[mock_order],
                    **mock_kwargs,
                )

            # Use the callback to make assertions on the request bodies
            response_list = []
            for mock_order in sorted(responses.keys()):
                response_list.append(
                    {
                        "headers": responses[mock_order]["headers"],
                        "json": functools.partial(
                            self.mock_response_callback,
                            responses[mock_order],
                        ),
                    },
                )

            with request_headers_path.open() as request_headers_opened:
                request_headers = json.load(request_headers_opened)
            request_mocks.setdefault(url_split.geturl(), {})[method] = (
                self.requests_mock.register_uri(
                    method=method,
                    url=url_split.geturl(),
                    complete_qs=True,
                    request_headers=request_headers,
                    response_list=response_list,
                ),
                responses,
            )
        return request_mocks

    def assert_request_mocks(self, request_mocks):
        """
        Assert that all request mocks have been called and each only once.
        """
        for methods in request_mocks.values():
            for request_mock, mock_responses in methods.values():
                self.assert_request_mock(request_mock, mock_responses)

    def assert_request_mock(self, request_mock, mock_responses):  # pragma: no cover
        """
        Assert that one request mock has been called once for each response.
        """
        mock_method = request_mock._method  # pylint: disable=protected-access
        mock_url = request_mock._url  # pylint: disable=protected-access
        if request_mock.call_count < len(mock_responses):
            response_contents = []
            for response_params in mock_responses.values():
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
                f"Some response mocks not called: {mock_method} {mock_url}",
            )
        elif request_mock.call_count > len(mock_responses):
            request_contents = []
            for mock_call in request_mock.request_history:
                request_content = mock_call.text
                if "Accept" in mock_call.headers:
                    _, minor_type = parse_content_type(
                        mock_call.headers["Accept"],
                    )
                    if minor_type.lower() == "json":
                        request_content = mock_call.json()
                request_contents.append(request_content)
            self.assertEqual(
                request_contents[: len(mock_responses)],
                request_contents,
                f"More requests than mocks: {mock_method} {mock_url}",
            )

    def mock_download_client_complete_item(
        self,
    ):
        """
        Simulate the download client finishing a download by moving the item.
        """
        self.servarr_downloaded_dir.mkdir(parents=True, exist_ok=True)
        return self.incomplete_item.rename(
            self.servarr_downloaded_dir / self.incomplete_item.name,
        )

    def mock_move_torrent_response(
        self,
        request=None,
        context=None,
        response_mock=None,
        delay=0,
    ):
        """
        Simulate the download client changing a download items location.
        """
        location = pathlib.Path(request.json()["arguments"]["location"])
        location.mkdir(parents=True, exist_ok=True)
        dst = location / self.downloaded_item.name
        if delay:
            # Simulate a delay using a subprocess
            self.addCleanup(
                subprocess.Popen(  # nosec B603, pylint: disable=consider-using-with
                    args=[
                        sys.executable,
                        "-c",
                        "import pathlib; "
                        f"import time; time.sleep({delay}); "
                        f"pathlib.Path('{self.downloaded_item}').rename('{dst}');",
                    ],
                ).communicate,
            )
        else:
            self.downloaded_item.rename(dst)
        context.headers.update(response_mock.get("headers", {}))
        return response_mock["from_mock_dir"]["json"]

    def mock_servarr_import_item(self, download_item=None):
        """
        Simulate Servarr importing a downloaded item, hardlink files into the library.
        """
        if download_item is None:
            download_item = self.downloaded_item
        self.imported_item_file.parent.mkdir(parents=True, exist_ok=True)
        imported_files = []
        for suffix, mime_type in mimetypes.types_map.items():
            if not mime_type.startswith("video/"):
                continue
            for downloaded_item_file in download_item.glob(f"**/*{suffix}"):
                downloaded_item_imported_file = (
                    self.imported_item_file.parent / downloaded_item_file.name
                )
                downloaded_item_imported_file.hardlink_to(downloaded_item_file)
                imported_files.append(downloaded_item_imported_file)
        return imported_files

    def mock_servarr_delete_file(self, imported_item_file=None):
        """
        Simulate Servarr deleting a file by deleting the file from the library.

        Assumes the only difference between Servarr importing an upgrade for the file
        and a user deleting the file through the UI is in the Servarr history.
        """
        imported_item_file = self.imported_item_file
        return imported_item_file.unlink()

    def mock_get_torrent_response(
        self,
        fields,
        request=None,
        context=None,
        response_mock=None,
    ):  # pylint: disable=unused-argument
        """
        Simulate a `torrent-get` request but modify the given fields.

        Useful for testing download item properties that can't be represented in static
        files such as date/time values.
        """
        for torrent, torrent_fields in zip(
            response_mock["from_mock_dir"]["json"]["arguments"]["torrents"],
            fields,
        ):
            torrent.update(torrent_fields)
        return response_mock["from_mock_dir"]["json"]
