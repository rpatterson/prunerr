# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Run Prunerr commands across multiple Servarr instances and download clients.
"""

import gc
import os
import time
import pathlib
import logging
import typing

import yaml
import tenacity
import transmission_rpc

import prunerr.downloadclient
import prunerr.servarr
from . import utils
from .utils import cached_property

logger = logging.getLogger(__name__)


class PrunerrValidationError(Exception):
    """
    Incorrect Prunerr configuration.
    """


class PrunerrRunner:
    """
    Run Prunerr sub-commands across multiple Servarr instances and download clients.
    """

    EXAMPLE_CONFIG = pathlib.Path(__file__).parent / "home" / ".config" / "prunerr.yml"

    config: dict
    quiet = False

    def __init__(self, config):
        """
        Capture a reference to the global Prunerr configuration file.
        """
        self.config_file = pathlib.Path(config)

        # Initialize any local instance state
        self.download_clients = {}
        self.servarrs = {}

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(utils.RETRY_EXC_TYPES),
        wait=tenacity.wait_fixed(1),
        reraise=True,
        before_sleep=tenacity.before_sleep_log(logger, logging.ERROR),
    )
    def update(self) -> dict:
        """
        Connect to the download and Servarr clients, waiting for reconnection on error.

        Aggregate all download clients from all Servarr instances defined in the config.

        :return: Map download client URLs to
            ``prunerr.downloadclient.PrunerrDownloadClient`` instances
        :raises PrunerrValidationError: The YAML configuration file has a problem
        """
        # Refresh the Prunerr configuration from the file
        if not self.config_file.is_file():
            raise PrunerrValidationError(
                f"Configuration file not found: {self.config_file}"
            )
        with self.config_file.open(encoding="utf-8") as config_opened:
            self.config = yaml.safe_load(config_opened)
        if not self.config.get("download-clients", {}).get("urls"):
            raise PrunerrValidationError(
                "Configuration file must include at least one URL under"
                f" `download-clients/urls`: {self.config_file}"
            )

        # Update Servarr API clients
        servarrs = {}
        for servarr_name, servarr_config in self.config.get("servarrs", {}).items():
            servarr_config.setdefault("name", servarr_name)
            servarrs[
                utils.normalize_url(servarr_config["url"])
            ] = prunerr.servarr.PrunerrServarrInstance(self)
            servarrs[servarr_config["url"]].update(servarr_config)
        self.servarrs = servarrs

        # Update download client RPC clients
        # Download clients not connected to a Servarr instance
        download_client_configs = dict(
            prunerr.downloadclient.config_from_url(download_client_auth_url)
            for download_client_auth_url in self.config["download-clients"]["urls"]
        )
        # Reconcile with download clients defined in Servarr settings
        for servarr in self.servarrs.values():
            for download_client_url in servarr.download_clients.keys():
                download_client_configs[download_client_url].setdefault(
                    "servarrs",
                    set(),
                ).add(servarr.config["url"])
        # Update the download clients, instantiating if newly defined
        download_clients = {}
        for (
            download_client_url,
            download_client_config,
        ) in download_client_configs.items():
            if download_client_url in self.download_clients:
                # Preserve any cached state in existing download clients
                download_clients[download_client_url] = self.download_clients[
                    download_client_url
                ]
            else:
                # Instantiate newly defined download clients
                download_clients[
                    download_client_url
                ] = prunerr.downloadclient.PrunerrDownloadClient(self)
            # Associate with Servarr instances
            for servarr_url in download_client_config.get("servarrs", set()):
                self.servarrs[servarr_url].download_clients[
                    download_client_url
                ].download_client = download_clients[download_client_url]
            download_clients[download_client_url].update(download_client_config)
        self.download_clients = download_clients

        return self.download_clients

    @cached_property
    def example_confg(self) -> dict:
        """
        Use the example configuration file for defaults where needed.

        :return: The configuration file YAML as Python values
        """
        with self.EXAMPLE_CONFIG.open() as config_opened:
            return yaml.safe_load(config_opened)

    # Sub-commands

    def exec_(self) -> typing.Optional[dict]:
        """
        Run the standard series of Prunerr operations once.

        :return: Map exec operations to those operations' results
        """
        # Results relies on preserving key order
        results = {}

        # Start verifying corrupt torrents as early as possible to give them as much
        # time to finish as possible.
        self.verify()

        # Run `review` before `move` so it can make any changes to download items before
        # they're moved and excluded from future review.
        # Also run before `free-space` in case it removes items.
        if "reviews" in self.config.get(  # pylint: disable=magic-value-comparison
            "indexers", {}
        ):
            if (review_results := self.review()) is not None:
                results["review"] = review_results

        # Run `move` before `free-spacce` so that all download items that could be
        # eligible for deletion are in the `seeding` directory.
        if move_results := self.move():
            results["move"] = move_results

        if free_space_results := self.free_space():
            results["free-space"] = free_space_results

        if results:
            return results
        return None

    def verify(self) -> dict:
        """
        Verify and resume download items flagged as having corrupt data.

        :return: Map download client URLs to verified download items
        """
        verify_results = {}
        for download_client_url, download_client in self.download_clients.items():
            if verifying_items := download_client.verify_corrupt_items():
                verify_results[download_client_url] = verifying_items
        return verify_results

    def move(self) -> dict:
        """
        Move download items that have been acted on by Servarr into the seeding dir.

        :return: Map download client URLs to moved download items
        """
        move_results: dict = {}
        for servarr_url, servarr in self.servarrs.items():
            for (
                download_client_url,
                servarr_download_client,
            ) in servarr.download_clients.items():
                if download_client_results := servarr_download_client.move():
                    move_results.setdefault(servarr_url, {})[
                        download_client_url
                    ] = download_client_results
        return move_results

    def review(self) -> typing.Optional[dict]:
        """
        Apply configured review operations to all download items.

        :return: Map download client URLs to the results of any review
            actions taken
        """
        # Combine all Servarr API download queue records.
        servarr_queue = {}
        for servarr in self.servarrs.values():
            servarr_queue.update(servarr.queue)
        # Delegate the rest to the download client
        review_results = {}
        for download_client_url, download_client in self.download_clients.items():
            if download_client_results := download_client.review(servarr_queue):
                review_results[download_client_url] = download_client_results
        if review_results:
            return review_results
        return None

    def free_space(self) -> typing.Optional[dict]:
        """
        If running out of disk space, delete some torrents until enough space is free.

        Delete from the following groups of torrents in order:
        - torrents no longer registered with the tracker
        - orphaned paths not recognized by the download client or its items
        - seeding torrents, that have been successfully imported

        :return: Map download client URLs to removed download items
        """
        # Some parts of freeing space, such as finding orphans, have to aggregate
        # download item details from all download clients.  Also, some operations for
        # one download client may affect the free space for other download clients, such
        # as deleting download items.  As such we can't delegate the whole process to
        # the download clients, only some parts of it.

        # TODO: Keep track of the required free space to decide when to stop deleting to
        # reduce the number and time cost of download client session RPC requests?
        # Premature optimization?

        if not (download_clients := self.free_space_download_clients()):
            return None

        results: dict = {}

        logger.info(
            "Deleting download items no longer registered with tracker to free space",
        )
        # If there are items to delete, then after deleting each item, refresh the
        # download client free space and list of download items and repeat until either
        # there are no more download items to delete or the download client has
        # sufficient free space.
        if not (
            download_clients := self.free_space_remove_items(
                download_clients,
                results,
                "find_unregistered",
            )
        ):
            return results

        logger.info(
            "Deleting orphaned files not belonging to any download item to free space",
        )
        for orphan_download_clients, file_path, file_stat in self.find_orphans():
            first_download_client = next(iter(orphan_download_clients.values()))
            first_download_client.delete_files((file_path, file_stat))
            results.setdefault(
                first_download_client.config["url"],
                [],
            ).append(str(file_path))
            # Do any download clients still need to free space?
            if not (download_clients := self.free_space_download_clients()):
                return results

        logger.info(
            "Deleting seeding download items to free space",
        )
        download_clients = self.free_space_remove_items(download_clients, results)
        if not download_clients:
            return results

        for download_client_url, download_client in download_clients.items():
            logger.error(
                "Insufficient free space for %r but nothing can be deleted: %0.2f %s",
                download_client_url,
                *transmission_rpc.utils.format_size(
                    download_client.config["min-free-space"]
                    - download_client.client.session.download_dir_free_space,
                ),
            )
            kwargs = {"speed_limit_down": 0, "speed_limit_down_enabled": True}
            # TODO: Notification when downloading is paused
            logger.info("Stopping downloading: %s", kwargs)
            download_client.client.set_session(**kwargs)

        return results

    def daemon(self):
        """
        Prune download client items continuously.
        """
        # Log only once at the start messages that would be noisy if repeated for every
        # daemon poll loop.
        self.quiet = False
        while True:  # pylint: disable=while-used
            # Start the clock for the poll loop as early as possible to keep the inner
            # loop duration as accurate as possible.
            start = time.time()

            try:  # pylint: disable=too-many-try-statements
                # Refresh the list of download items
                self.update()
                # Resume any corrupt download items that have finished verifying
                self.resume_verified_items()
                # Run the `exec` sub-command as the inner loop
                self.exec_()
            except utils.RETRY_EXC_TYPES as exc:  # pragma: no cover
                logger.error(
                    "Connection error while updating from server: %s",
                    exc,
                )
                # Re-connect to external services and retry
            else:
                # Don't repeat noisy messages from now on.
                self.quiet = True
            logger.debug("Sub-command `exec` completed in %ss", time.time() - start)

            # Determine the poll interval before clearing the config
            poll = self.config.get("daemon", {}).get("poll", 60)

            # Free any memory possible between daemon loops
            self.clear()

            # Wait for the next interval
            if (time_left := poll - (time.time() - start)) > 0:
                time.sleep(time_left)
            logger.debug("Sub-command `daemon` looping after %ss", time.time() - start)

    # Other methods

    def free_space_download_clients(self) -> dict:
        """
        Return all download clients that don't have sufficient free space.

        :return: Map download client URLs to
            ``prunerr.downloadclient.PrunerrDownloadClient`` instances without
            sufficient free space
        """
        return {
            download_client_url: download_client
            for download_client_url, download_client in self.download_clients.items()
            if not download_client.free_space_maybe_resume()
        }

    def free_space_remove_items(
        self,
        download_clients: dict,
        results: dict,
        download_client_method: str = "find_seeding",
    ) -> dict:
        """
        Delete download items until sufficient space is free the items are exhausted.

        If there are items to delete, then after deleting each item, refresh the
        download clients free space and lists of download items and repeat until either
        there are no more download items to delete or all download clients have
        sufficient free space.

        :param download_clients: The download clients from which to delete download
            items
        :param results: Map download client URLs to deleted download item hashes
        :param download_client_method: The
            ``prunerr.downloadclient.PrunerrDownloadClient`` method from which to
            retrieve download items to delete
        :return: Map download client URLs to
            ``prunerr.downloadclient.PrunerrDownloadClient`` instances that still have
            insufficient free space
        """
        while download_clients:  # pylint: disable=while-used
            for download_client_url, download_client in download_clients.items():
                removed_size = None
                for download_item in getattr(
                    download_client,
                    download_client_method,
                )():
                    removed_size = download_client.delete_files(download_item)
                    results.setdefault(
                        download_client_url,
                        [],
                    ).append(download_item.hashString)
                    download_clients = self.free_space_download_clients()
                    break
                if removed_size:
                    break
            else:
                break
        return download_clients

    def find_orphans(self) -> list:
        """
        Find paths in download client directories that don't correspond to an item.

        Iterate through all the paths managed by each download client in turn, check
        all paths within those directories against the download items known to the
        download client, and report all paths that are unknown to the download client.

        Useful to identify paths to delete when freeing disk space.  Returned sorted
        from paths that use the least disk space to the most.

        :return: A list of orphaned filesystem paths
        """
        # Collect all the download item files that actually exist currently
        item_files: set = set()
        for download_client_url, download_client in self.download_clients.items():
            for download_item in download_client.items:
                item_files.update(
                    item_file.path
                    for item_file in download_item.files
                    if item_file.path.exists()
                )

        # Aggregate all the download item directories across all download clients.  Some
        # download item directories may be shared across download clients and some may
        # be on different filesystems so we need to aggregate them all across download
        # clients but keep track of which download clients use which directories.
        download_item_dirs: dict = {}
        # TODO: Consider all orphans under the download client directories, not just the
        # Servarr managed directories
        for download_client_url, download_client in self.download_clients.items():
            for servarr_download_client in download_client.servarrs.values():
                for download_item_dir in (
                    servarr_download_client.download_dir,
                    servarr_download_client.seeding_dir,
                ):
                    download_item_dirs.setdefault(download_item_dir, {})[
                        download_client_url
                    ] = download_client

        # Collect any files in any download item directories that aren't download item
        # files.  Also yield the download clients that the file's download item
        # directory use.  Also yield the `stat` syscall results for that file to reduce
        # such syscalls downstream.
        orphans = []
        for download_item_dir, download_clients in download_item_dirs.items():
            for dirpath, _, filenames in os.walk(download_item_dir):
                for filename in filenames:
                    file_path = download_item_dir / dirpath / filename
                    if file_path not in item_files:
                        orphans.append(
                            (download_clients, file_path, file_path.stat()),
                        )

        # Order orphans by smallest size first.  Use this sort order to give the user as
        # long as possible to rescue any larger, and thus harder to restore, files.
        # Also cleans up noisy small file clutter first.
        orphans.sort(key=lambda orphan: orphan[2].st_size)

        return orphans

    def resume_verified_items(self, wait: bool = False) -> dict:
        """
        Resume downloading any previously corrupt items that have finished verifying.

        Optionally wait until all verifying items have finished and resume them all.

        :param wait: Whether to block until verifying items finish
        :return: Map download client URLs to resumed download items
        """
        resume_results = {}
        for download_client_url, download_client in self.download_clients.items():
            resumed_items = list(download_client.resume_verified_items().values())
            if wait:
                while download_client.verifying_items:  # pylint: disable=while-used
                    time.sleep(1)
                    resumed_items.extend(download_client.resume_verified_items())
            if resumed_items:
                resume_results[download_client_url] = resumed_items
        return resume_results

    def clear(self):
        """
        Free any memory possible between daemon loops.
        """
        del self.config
        self.servarrs.clear()
        # Clear discreet download client caches to preserve verifying download items
        for _, download_client in self.download_clients.items():
            del download_client.config
            del download_client.operations
            del download_client.client
            download_client.servarrs.clear()
            del download_client.items
        # Tell Python it's a good time to free memory
        gc.collect()
