"""
Tests for Prunerr.
"""

import os
import re
import pathlib
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

    # HTTP methods taken from /usr/lib/python3.10/wsgiref/validate.py:340
    HTTP_METHODS_RE = re.compile("^(GET|HEAD|POST|OPTIONS|PATCH|PUT|DELETE|TRACE)")

    HOME = pathlib.Path(prunerr.__path__[0]).parents[1] / "home"
    CONFIG = HOME / ".config" / "prunerr.yml"
    ENV = {
        "HOME": str(HOME),
        "DEBUG": "true",
    }

    # The set of request responses to mock
    RESPONSES_DIR = pathlib.Path(__file__).parent / "responses" / "default"

    # Download client path elements
    STORAGE_RELATIVE = pathlib.PurePath("media", "Library")
    INCOMPLETE_DIR_BASENAME = "incomplete"
    DOWNLOADED_DIR_BASENAME = "downloads"
    SEEDING_DIR_BASENAME = "seeding"
    EXAMPLE_VIDEO = pathlib.Path(__file__).parent / "example-5s.mkv"

    # Servarr path elements
    SERVARR_TYPE = "sonarr"
    SERVARR_STORAGE_RELATIVE = pathlib.PurePath("Videos", "Series")
    SERVARR_IMPORT_PARENT_BASENAME = "Season 01"
    SERVARR_DIR_TITLE = "Foo Series (1970)"

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
        self.seeding_dir = self.storage_dir / self.SEEDING_DIR_BASENAME

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

        if self.download_client_urls[0] in self.download_client_items_responses:
            self.set_up_download_item(
                self.download_client_items_responses[self.download_client_urls[0]][
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
        self.incomplete_item_data = self.incomplete_item.with_name(
            f"{self.incomplete_item.name}"
            f"{prunerr.downloadclient.PrunerrDownloadClient.DATA_FILE_EXT}",
        )
        self.downloaded_item = self.servarr_downloaded_dir / self.download_item_title
        self.downloaded_item_file = (
            self.downloaded_item / self.incomplete_item_file.name
        )
        self.downloaded_item_data = self.downloaded_item.with_name(
            self.incomplete_item_data.name,
        )
        self.seeding_item = self.servarr_seeding_dir / self.download_item_title
        self.seeding_item_file = self.seeding_item / self.incomplete_item_file.name
        self.seeding_item_data = self.seeding_item.with_name(
            self.downloaded_item_data.name,
        )
        if self.SERVARR_IMPORT_PARENT_BASENAME:
            self.imported_item_file = (
                self.servarr_import_dir
                / self.SERVARR_IMPORT_PARENT_BASENAME
                / self.incomplete_item_file.name
            )
        else:
            self.imported_item_file = (
                self.servarr_import_dir / self.incomplete_item_file.name
            )

    def set_up_download_item_files(self, download_client_url):
        """
        Copy example files into place to represent download item files.
        """
        download_client_url = urllib.parse.urlsplit(download_client_url)
        torrent_list_mocks = list(
            (
                self.RESPONSES_DIR
                / download_client_url.scheme
                / urllib.parse.quote(download_client_url.netloc)
                / urllib.parse.quote(download_client_url.path.lstrip(os.path.sep))
                / "rpc"
                / "POST"
            ).glob("*-torrent-get")
        )
        if not torrent_list_mocks:
            return
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
                scheme=url_unquoted_path.parents[-2].name,  # pylint: disable=no-member
                netloc=url_unquoted_path.parents[-3].name,  # pylint: disable=no-member
                path=url_path_split.path,
                query=url_path_split.query,
                fragment=url_path_split.fragment,
            )

            responses = {}
            for response_path in request_headers_path.parent.glob("*/response.*"):
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

                responses[response_path.parent.name] = dict(
                    headers=response_headers,
                    content=response_bytes,
                )

            # Insert any manual mocks in the right order.  Useful for dynamic callback
            # mocks such as requesting the download client to move download items.
            if manual_mocks is not None:
                responses.update(
                    manual_mocks.get(url_split.geturl(), {}).get(method, {}),
                )
            responses = [
                responses[mock_order] for mock_order in sorted(responses.keys())
            ]

            with request_headers_path.open() as request_headers_opened:
                request_headers = json.load(request_headers_opened)
            request_mocks.setdefault(url_split.geturl(), {})[method] = (
                self.requests_mock.register_uri(
                    method=method,
                    url=url_split.geturl(),
                    complete_qs=True,
                    request_headers=request_headers,
                    response_list=responses,
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

    def assert_request_mock(self, request_mock, mock_responses):
        """
        Assert that one request mock has been called once for each response.
        """
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
                    _, minor_type = parse_content_type(
                        mock_call.headers["Accept"],
                    )
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

    def mock_download_client_complete_item(
        self,
        servarr_type=None,
        incomplete_item=None,
    ):
        """
        Simulate the download client finishing a download by moving the item.
        """
        if servarr_type is None:
            servarr_type = self.SERVARR_TYPE
        if incomplete_item is None:
            incomplete_item = self.incomplete_item
        self.servarr_downloaded_dir.mkdir(parents=True, exist_ok=True)
        return incomplete_item.rename(
            self.servarr_downloaded_dir / incomplete_item.name,
        )

    def mock_move_torrent_response(self, request, _):
        """
        Simulate the download client changing a download items location.
        """
        location = pathlib.Path(request.json()["arguments"]["location"])
        location.mkdir(parents=True, exist_ok=True)
        self.downloaded_item.rename(location / self.downloaded_item.name)
        return {"arguments": {}, "result": "success"}

    def mock_servarr_import_item(self, servarr_type=None, downloaded_item=None):
        """
        Simulate Servarr importing a downloaded item, hardlink files into the library.
        """
        if servarr_type is None:
            servarr_type = self.SERVARR_TYPE
        if downloaded_item is None:
            downloaded_item = self.downloaded_item
        self.imported_item_file.parent.mkdir(parents=True, exist_ok=True)
        imported_files = []
        for ext, mime_type in mimetypes.types_map.items():
            if not mime_type.startswith("video/"):
                continue
            for downloaded_item_file in downloaded_item.glob(f"**/*{ext}"):
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
        if imported_item_file is None:
            imported_item_file = self.imported_item_file
        return imported_item_file.unlink()
