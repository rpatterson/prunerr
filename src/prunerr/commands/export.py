# SPDX-FileCopyrightText: 2024 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Link imported files back into download items and verify, Servarr import inverse.
"""

import typing
import subprocess  # nosec, pragmatic choice for performance
import logging

import requests
import transmission_rpc

import prunerr.servarr.rootitem
import prunerr.servarr.release
from ..utils import pathlib
from .. import utils
from .. import downloaditem

logger = logging.getLogger(__name__)


class ExportCommandRun:
    """
    Represent the state and logic of an individual run of the ``export`` sub-command.
    """

    download_ids: dict

    def __init__(self, servarr):
        """
        Capture a reference to the Servarr instance.

        :param servarr: The ``prunerr.servarr.PrunerrServarrInstance`` object
            representing the specific Servarr instance.
        """
        self.servarr = servarr

    def update(self):
        """
        Process command-line arguments and collate global download items data.
        """
        # Collect global download item data shared between series/movies:
        # TODO: Re-use something in `pruner.servarr.*`?
        self.download_ids = {}
        for servarr_download_client in self.servarr.download_clients.values():
            for release in servarr_download_client.releases:
                self.download_ids.setdefault(
                    release.download_item.hash_string.upper(),
                    [],
                ).append(release)

    def __call__(self) -> typing.Optional[dict]:
        """
        Link imported files back into download items and verify, Servarr import inverse.

        #. Get the latest import and grab history records for every currently imported
           file in the library.

        #. Collect the unique download item IDs from all the grab records.

        #. Ensure that the download client currently has the download item for each
           download item ID, re-adding the item paused if necessary.

        #. For import records that have no grab records, such as manual imports, get
           their download item IDs by matching on download item name.

        #. Locate existing download item data in known directories and set the most
           recently modified as the download item's location.

        #. For each imported file, ensure it's hard-linked into the download client for
           every download client that has that download item.

        #. Deselect for download any remaining incomplete files.

        #. Verify and resume the download item.

        :return: Map series/movies to the relative paths of any imported files that were
            linked into the download item.
        """
        # Start with collated grab and import history for each series/movie:
        export_results = {}
        for servarr_root_item in self.servarr.client.get(
            self.servarr.type_map["dir_type"],
        ):
            export_root_item = ExportServarrRootItem(
                self,
                prunerr.servarr.rootitem.PrunerrServarrRootItem(
                    self.servarr,
                    servarr_root_item["id"],
                ),
            )
            export_root_item.update(servarr_root_item)
            if linked_files := export_root_item():
                export_results[servarr_root_item["title"]] = linked_files

        # Report results if any:
        if export_results:
            return export_results
        return None


class ExportServarrRootItem:
    """
    Represent the state and logic of exporting one Servarr series/movie/etc..
    """

    imported_download_ids: dict

    def __init__(
        self,
        command_run,
        root_item: "prunerr.servarr.rootitem.PrunerrServarrRootItem",
    ):
        """
        Capture references to this `export` sub-command run and Servarr series/movie.

        :param command_run: The ``ExportCommandRun`` object representing this run of the
            ``$ prunerr export`` sub-command.
        :param root_item: The Prunerr representation a root Servarr item, for example a
            series or movie.
        """
        self.command_run = command_run
        self.root_item = root_item

    def update(self, data: dict):
        """
        Get and collate the data export requires from the Servarr API.

        :param data: The dictionary from the Servarr API JSON for the top-level
            library item, for example series or movie.
        """
        # Assemble the series/movie data that is different for `export` from `apply`:
        self.root_item.data = data

        # Map imported file paths missing download item IDs/hashes by further
        # methods with the collated history data:
        self.lookup_download_ids()

        # Now group the imported files under the download item IDs/hashes the come from
        # them:
        self.imported_download_ids = {}
        for imported_id in self.root_item.history.imported_items:
            imported_collated = self.root_item.history.imported_ids.get(imported_id, {})
            if not (
                imported_collated.get("downloadId")
                and imported_collated.get("droppedRel")
            ):
                # Logged in `lookup_download_ids()`:
                continue
            self.imported_download_ids.setdefault(
                imported_collated["downloadId"],
                {},
            ).setdefault(imported_id, imported_collated)

    def __call__(self):
        """
        Link imported files back into download items for one series/movie.

        :param mapped_download_items: Map download items by hashes, names and root
            basenames.
        :return: The download item file paths of any imported files that were linked
            into the download item.
        """
        # Add download items to the client now that we've done everything we can to
        # identify any download items that aren't already in the client:
        added_items = {}
        for download_id in self.imported_download_ids:
            # Next, ensure all download hashes are in the download client, re-adding the
            # items if necessary:
            added_item = maybe_add_download_item(
                self.command_run.download_ids,
                download_id,
                self.root_item.history.download_ids.get(download_id, {}).get(
                    "downloadUrl", {}
                ),
            )
            if added_item is not None:
                added_items[added_item.hash_string] = added_item

        # As a last resort, map any imported paths without download item IDs by the
        # pre-existing download item names and root basenames in the client:
        for releases in self.command_run.download_ids.values():
            for release in releases:
                # TODO: Move to Servarr property?
                for download_file in release.download_item.files:
                    self.root_item.history.dropped_relatives.setdefault(
                        download_file.relative,
                        {},
                    ).setdefault(
                        "downloadId", release.download_item.hash_string.upper()
                    )
        for (
            download_id,
            imported_ids,
        ) in self.lookup_download_ids().items():
            self.imported_download_ids.setdefault(download_id, {}).update(
                imported_ids,
            )

        # Finally, hard link imported files into the download items:
        linked_files = []
        for download_id, imported_ids in self.imported_download_ids.items():
            for release in self.command_run.download_ids.get(
                download_id,
                [],
            ):
                linked_files.extend(
                    self.link_imported_files(
                        release,
                        imported_ids,
                        need_verify=download_id.lower() in added_items,
                    ),
                )
        return linked_files

    def lookup_download_ids(self) -> dict:
        """
        Lookup the download IDs for imported files without them by download item name.

        :return: Map download item names and root basenames to download item hash IDs.
        """
        download_ids: dict = {}
        release_hashes_by_root: set = set()
        for (
            imported_id,
            imported_item,
        ) in self.root_item.history.imported_items.items():
            download_id = self.root_item.history.imported_ids.get(
                imported_id,
                {},
            ).get("downloadId")
            if download_id:
                # Already found a download item hash ID by better means:
                continue

            download_id = self.lookup_download_id(
                release_hashes_by_root,
                imported_id,
                imported_item,
            )
            if download_id:
                download_ids.setdefault(download_id, {}).setdefault(
                    imported_id,
                    self.root_item.history.imported_ids.get(imported_id, {}),
                )
                self.root_item.history.imported_ids[imported_id].setdefault(
                    "downloadId",
                    download_id,
                )

        return download_ids

    def lookup_download_id(
        self,
        release_hashes_by_root: set,
        imported_id: pathlib.Path,
        imported_item: dict,
    ) -> typing.Optional[str]:
        """
        Lookup the download IDs for imported files without them by download item name.

        :param release_hashes_by_root:
            The dropped path root basenames that have already been matched.
        :param imported_id: The relative path to the imported file within the
            series/movie.
        :param imported_item: The Servarr API JSON object for the imported item
            annotated with the imported file object.
        :return: The download item hash ID if one matched by name or root basename.
        """
        imported_collated = self.root_item.history.imported_ids.get(imported_id, {})
        dropped_relative = imported_collated.get("droppedRel")

        if download_id := self.root_item.history.dropped_relatives.get(
            dropped_relative,
            {},
        ).get("downloadId"):
            if dropped_relative.parts[0] in release_hashes_by_root:
                logger.debug(  # pragma: no cover
                    "Matched download item by dropped relative path: %s",
                    dropped_relative,
                )
            else:
                logger.info(
                    "Matched download item by dropped relative path: %s",
                    dropped_relative,
                )

        if download_id:
            release_hashes_by_root.add(dropped_relative.parts[0])
            return download_id

        logger.error(
            "Could not lookup download item by names: %s",
            imported_item["file"]["path"],
        )
        return None

    def link_imported_files(
        self,
        release: prunerr.servarr.release.PrunerrServarrRelease,
        imported_ids: dict,
        need_verify: bool = False,
    ) -> list:
        """
        Hard link imported files back into download items.

        :param release: The download item whose files to link.
        :param imported_ids: Map the relative paths of imported files to the
            corresponding paths within the download item.
        :param need_verify: Optionally pass in whether the caller already knows this
            item needs to be verified after linking.
        :return: The download item file paths of any imported files that were linked
            into the download item.
        """
        # Change the download item data path if a better one is found.  Collect
        # additional possible data paths from the import history records:
        item_suffix_path = (
            release.servarr_download_client.download_dir_suffix
            / release.download_item.root_name
        )
        if not (
            item_root_paths := list(
                release.download_item.download_client.download_dir.parent.glob(
                    f"*/{utils.fnmatch_escape(str(item_suffix_path))}",
                ),
            )
        ):
            logger.debug(
                "No existing download item location found for: %r",
                release.download_item,
            )
        elif find_location(release.download_item, item_root_paths):
            need_verify = True

        # Hard link imported files into the download item's location:
        linked_files = []
        for imported_id, dropped_data in imported_ids.items():
            if (  # pragma: no cover
                dropped_data["droppedRel"]
                not in release.download_item.files_by_relative
            ):
                logger.error(
                    "Dropped path doesn't match download item file: %s",
                    dropped_data["droppedRel"],
                )
                continue
            if (
                release.download_item.FIELD_DOWNLOAD_DIR
                not in release.download_item.fields
            ):  # pragma: no cover
                logger.debug(
                    "Missing download dir field, updating: %r",
                    release.download_item,
                )
                release.download_item.update()

            # Also export any Servarr extra sibling files that may have been imported:
            # TODO: Servarr and media library apps may modify some download file types
            # such as `*.nfo* and `*.jpg` so an argument could be made these should
            # *not* be linked back into the download items. OTOH, some configurations
            # may import and preserve such download item files so it's not clear what
            # the best approach here is:
            imported_path = self.root_item.imported_items[imported_id]["file"]["path"]
            for imported_sibling in imported_path.parent.glob(
                f"{utils.fnmatch_escape(imported_path.stem)}*",
            ):
                download_sibling_relative = dropped_data["droppedRel"].with_name(
                    f"{dropped_data['droppedRel'].stem}"
                    f"{imported_sibling.name[len(imported_path.stem):]}",
                )
                download_sibling = (
                    release.download_item.download_dir / download_sibling_relative
                )
                if (
                    imported_sibling.exists()
                    and (
                        download_sibling_relative
                        in release.download_item.files_by_relative
                    )
                    and maybe_link_file(download_sibling, imported_sibling)
                ):
                    need_verify = True
                    linked_files.append(str(download_sibling))

        if need_verify:
            # Deselect for download any remaining incomplete files:
            release.download_item.clear()
            deselected_files = deselect_un_imported_files(release.download_item)
            if len(deselected_files) == len(release.download_item.files):
                logger.error(  # pragma: no cover
                    "No files imported, not verifying or resuming: %r",
                    release.download_item,
                )
            else:
                logger.info(
                    "Verifying and resuming download item: %r",
                    release.download_item,
                )
                release.download_item.download_client.client.verify_torrent(
                    release.download_item.hash_string,
                )
                release.download_item.download_client.client.start_torrent(
                    release.download_item.hash_string
                )

        return linked_files


def find_location(
    download_item: downloaditem.PrunerrDownloadItem, item_root_paths: list
) -> pathlib.Path:
    """
    Find the most downloaded data path for this download item and set location.

    The current implementation guesses the most downloaded path by sorting the
    possible matches by size, largest first, and then modification date, most recent
    first, and selects the first of those sorted paths. Anything more accurate
    requires CPU intensive, time consuming verification.

    :param download_item: The download item whose files to link.
    :param item_root_paths: Filesystem paths of existing download item data.
    :return: The best data path if the location was changed.
    """
    if download_item.FIELD_DOWNLOAD_DIR not in download_item.fields:  # pragma: no cover
        logger.debug(
            "Missing download dir field, updating: %r",
            download_item,
        )
        download_item.update()

    def key(item_root_path: pathlib.Path) -> tuple:
        """
        Determine the size and modification date of this items data in the path.

        :param item_root_path: A filesystem path of existing download item data.
        :return: The values on which to sort this sequence item.
        """
        du_process = subprocess.run(  # nosec, pragmatic choice for performance
            ["du", "-s", str(item_root_path)],
            capture_output=True,
            check=True,
        )
        return (
            int(du_process.stdout.strip().split()[0]),
            item_root_path.stat().st_mtime,
        )

    item_root_path = sorted(item_root_paths, reverse=True, key=key)[0]

    if download_item.download_dir != item_root_path.parent:
        logger.info(
            "Changing download item location for %r: %s",
            download_item,
            item_root_path.parent,
        )
        download_item.download_client.client.move_torrent_data(
            download_item.hash_string,
            item_root_path.parent,
            move=False,
        )
        # Avoid another RPC request, update the field value using the internals:
        download_item.fields[download_item.FIELD_DOWNLOAD_DIR] = str(
            item_root_path.parent
        )
        del download_item.download_dir
        return item_root_path.parent

    logger.debug(
        "Download item location already best for %r: %s",
        download_item,
        item_root_path.parent,
    )
    return None


def maybe_add_download_item(
    download_items_by_id: dict,
    download_id: str,
    download_urls: dict,
) -> typing.Optional[transmission_rpc.Torrent]:
    """
    Add a download item from the given URL if not already in the download client.

    :param download_items_by_id: Map download item hashes to the items.
    :param download_id: The download item hash ID.
    :param download_urls: The download item URLs mapped to the download client to add
        them to.
    :return: The download item whether added or existing or None if it could not be
        added.
    """
    if download_id in download_items_by_id:
        logger.debug(
            "Skipping already added torrent: %s",
            download_items_by_id[download_id][0].download_item.name,
        )
        return None
    if not download_urls:  # pragma: no cover
        logger.error(
            "No grab history found for download item ID/hash: %s",
            download_id,
        )
        return None

    # Try each download URL from the grab history, most recent first:
    for download_url, download_data in download_urls.items():
        try:
            added_item = download_data["downloadClient"].download_client.add_torrent(
                download_url,
                paused=True,
                download_dir=str(download_data["downloadClient"].seeding_dir),
            )
        except (  # pragma: no cover
            requests.exceptions.RequestException,
            transmission_rpc.error.TransmissionError,
        ):
            # Tolerate exceptions adding torrents because the download
            # URL may no longer be valid, IOW 404:
            logger.exception(
                "Exception adding torrent: %s",
                download_data.get("nzbInfoUrl") or download_url,
            )
            continue

        release = prunerr.servarr.release.PrunerrServarrRelease(
            download_data["downloadClient"],
            added_item,
        )
        download_items_by_id.setdefault(
            release.download_item.hash_string.upper(),
            [],
        ).append(release)
        return added_item

    return None  # pragma: no cover


def maybe_link_file(source: pathlib.Path, target: pathlib.Path) -> bool:
    """
    Link the source file to the target path if not already linked to it.

    :param source: The path of the file to hard link.
    :param target: The path to hard link the file to.
    :return: ``True`` if the source was hard linked.
    """
    try:
        source.parent.mkdir(parents=True, exist_ok=True)
    except OSError:  # pragma: no cover
        logger.exception(
            "Error creating download item directory: %s",
            source.parent,
        )
        return False
    if source.parent.stat().st_dev != target.parent.stat().st_dev:  # pragma: no cover
        logger.exception(
            "Download item on different filesystem: %r -> %r",
            str(source),
            str(target),
        )
        return False
    if source.exists():
        if source.samefile(target):
            logger.debug(
                "Already hard linked to file: %r -> %r",
                str(source),
                str(target),
            )
            return False
        logger.info(
            "Deleting existing file: %s",
            source,
        )
        source.unlink()
    logger.info(
        "Hard linking file: %r -> %r",
        str(source),
        str(target),
    )
    source.hardlink_to(target)
    return True


def deselect_un_imported_files(download_item: downloaditem.PrunerrDownloadItem) -> list:
    """
    For any un-imported and incomplete files, deselect them for download.

    :param download_item: The download item whose files to link.
    :return:
        Map file indexes to ``prunerr.downloaditem.PrunerrDownloadItemFile()``
        instances for any files that were deselected.
    """
    deselected_files = [
        download_file
        for download_file in download_item.files
        if (
            not download_file.exists
            or (
                download_file.stat.st_nlink <= 1
                and download_file.completed < download_file.size
            )
        )
    ]
    if deselected_files:
        logger.info(
            "Deselecting un-imported, incomplete download files for %r:\n  %s",
            download_item,
            "\n  ".join(repr(deselected_file) for deselected_file in deselected_files),
        )
        download_item.download_client.client.change_torrent(
            [download_item.hash_string],
            files_unwanted=[deselected_file.id for deselected_file in deselected_files],
        )
    return deselected_files
