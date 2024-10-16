# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Prunerr interaction with download clients.
"""

import os
import typing
import logging

from . import utils
from .utils import pathlib
from .utils import cached_property

if typing.TYPE_CHECKING:  # pragma: no cover
    import prunerr.servarr.release

logger = logging.getLogger(__name__)


class PrunerrDownloadFile(utils.PrunerrComponent):
    """
    Combine Prunerr's download item file access and the RPC client library's.
    """

    def __init__(self, download_item, rpc_file):
        """
        Capture a reference to the RPC client library item file.
        """
        self.download_item = download_item
        self.rpc_file = rpc_file

    def __getattr__(self, name):
        """
        Make `stat()` properties available as attributes.
        """
        try:
            return getattr(self.rpc_file, name)
        except AttributeError:  # pragma: no cover
            return getattr(self.stat, name)

    @property
    def details(self) -> dict:
        """
        Assemble all available useful information.

        :return: Map descriptive names to useful values.
        """
        details = {
            "path": self.rpc_file.name,
            "disk_usage": utils.format_size(self.disk_usage),
            "imported": self.is_imported,
        }
        return details

    @cached_property
    def relative(self) -> pathlib.Path:
        """
        Assemble the path for this item file relative to the item root.

        :return: The assembled path.
        """
        return pathlib.Path(self.rpc_file.name)

    @cached_property
    def path(self) -> pathlib.Path:
        """
        Determine this file's path, in the ``download-dir`` or ``incomplete-dir``.

        :return: The path found for this file.
        """
        path = self.download_item.parents[0] / self.relative
        if path.exists():
            return path
        for parent in self.download_item.parents[1:]:
            other_path = parent / self.relative
            if other_path.exists():
                return other_path
        return path

    @cached_property
    def exists(self) -> os.stat_result:
        """
        Check this download file's existence once and cache.

        Done to minimize repeated external syscalls across stage filters and operation
        templates.

        :return: The file's metadata.
        """
        return self.path.exists()

    @cached_property
    def stat(self) -> os.stat_result:
        """
        Lookup item file `stat` metadata only as needed and only once.

        :return: The file's metadata.
        """
        return self.path.stat()

    @cached_property
    def disk_usage(self) -> int:
        """
        Calculate the real storage usage of this file.

        Considering hard links and sparse files.

        :return: The size in bytes or B.
        """
        return (
            (self.stat.st_blocks * 512)
            if (self.exists and self.stat.st_nlink == 1)
            else 0
        )

    @cached_property
    def is_imported(self) -> bool:
        """
        Has this file been imported into the library by hard linking it elsewhere.

        :return: Whether this file has more than one hard link.
        """
        return self.exists and self.stat.st_nlink > 1

    @cached_property
    def is_servarr_extra(self) -> bool:
        """
        Is this an extra file that Servarr imports.

        :return: Whether this file is a Servarr extra import.
        """
        if self.download_item.release is not None:
            servarr = self.download_item.release.servarr_download_client.servarr
            return self.relative.suffix in servarr.extra_file_suffixes
        return False  # pragma: no cover

    @cached_property
    def is_lib_import(self) -> bool:
        """
        Is this a file imported to the Servarr library as an episode/movie.

        :return: Whether this file is a Servarr library item import.
        """
        # This is just an approximation. Users may have manually imported, or some other
        # app may have imported files with out an extension in `extraFileExtensions` but
        # that aren't Servarr library files. For example, if a user manually imports
        # `*/Featurettes/*.mkv` from a Radarr download item, those files will return
        # `True` from this property. If Prunerr ever grows a way to distinguish library
        # items with the same extension as non-library items, it should be used here:
        return self.is_imported and not self.is_servarr_extra

    @cached_property
    def queued_upgrades(self) -> dict:
        """
        Map the queued releases that will upgrade this file when imported.

        Only available for download items in the ``upgraded`` stage.

        :return: Map queued release download item hash IDs to the queued release item
            files that will upgrade this file.
        :raises NotImplementedError: There's a problem with the conditions that prevents
            identifying queued upgrades.
        """
        raise NotImplementedError(  # pragma: no cover
            "Cannot identify queued upgrades outside the ``upgraded`` stage"
            f": {self!r}",
        )
