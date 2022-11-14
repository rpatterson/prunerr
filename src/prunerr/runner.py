"""
Run Prunerr commands across multiple Servarr instances and download clients.
"""

# TODO: Reload config before each daemon loop run but preserve instance state containing
#       Servarr history

import os
import socket
import functools
import pathlib
import logging

import yaml
import tenacity
import transmission_rpc
import arrapi

import prunerr.downloadclient
import prunerr.servarr

logger = logging.getLogger(__name__)


class PrunerrRunner:
    """
    Run Prunerr sub-commands across multiple Servarr instances and download clients.
    """

    EXAMPLE_CONFIG = pathlib.Path(__file__).parent / "home" / ".config" / "prunerr.yml"

    download_clients = None
    servarrs = None
    quiet = False

    def __init__(self, config, servarr_name=None, replay=None):
        """
        Capture a reference to the global Prunerr configuration.
        """
        self.config = config
        self.servarr_name = servarr_name
        self.replay = replay

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(
            (
                socket.error,
                transmission_rpc.error.TransmissionError,
                arrapi.exceptions.ConnectionFailure,
            )
        ),
        wait=tenacity.wait_fixed(1),
        reraise=True,
        before_sleep=tenacity.before_sleep_log(logger, logging.DEBUG),
    )
    def connect(self):
        """
        Connect to the download and Servarr clients, waiting for reconnection on error.

        Aggregate all download clients from all Servarr instances defined in the config.
        """
        # Start with download clients not connected to a Servarr instance so that if
        # Servarr instances are connected to the same download client, the reference to
        # the servarr instance takes precedence.
        self.download_clients = {}
        for download_client_url in self.config.get("download-clients", {}).get(
            "urls", []
        ):
            self.download_clients[
                download_client_url
            ] = prunerr.downloadclient.PrunerrDownloadClient(
                self,
                {"url": download_client_url},
            )
            self.download_clients[download_client_url].connect()

        # Gather download clients from Servarr configuration via the Servarr API
        self.servarrs = {}
        for servarr_name, servarr_config in self.config.get("servarrs", {}).items():
            servarr_config.setdefault("name", servarr_name)
            self.servarrs[
                servarr_config["url"]
            ] = servarr = prunerr.servarr.PrunerrServarrInstance(self, servarr_config)
            servarr.connect()
            self.download_clients.update(
                (item[0], item[1].download_client)
                for item in servarr.download_clients.items()
            )

        return self.download_clients

    @functools.cached_property
    def example_confg(self):
        """
        Use the example configuration file for defaults where needed.
        """
        with self.EXAMPLE_CONFIG.open() as config_opened:
            return yaml.safe_load(config_opened)

    def exec_(self):
        """
        Run the standard series of Prunerr operations once.
        """
        results = {}
        # Relies on preserving key order
        results["sync"] = self.sync()
        results["free-space"] = self.free_space()
        return results

    def sync(self):
        """
        Synchronize the state of download client items with Servarr event history.
        """
        return {
            download_client_url: download_client.sync()
            for download_client_url, download_client in self.download_clients.items()
        }

    def free_space(self):
        """
        If running out of disk space, delete some torrents until enough space is free.

        Delete from the following groups of torrents in order:
        - torrents no longer registered with the tracker
        - orphaned paths not recognized by the download client or its items
        - seeding torrents, that have been successfully imported
        """
        # Some parts of freeing space, such as finding orphans, have to aggregate
        # download item details from all download clients.  Also, some operations for
        # one download client may affect the free space for other download clients, such
        # as deleting download items.  As such we can't delegate the whole process to
        # the download clients, only some parts of it.

        # TODO: Aggregate download clients by `file_path.stat().st_dev` to avoid
        # unnecessary download client session RPC requests?  Premature optimization?

        # TODO: Keep track of the required free space to decide when to stop deleting to
        # reduce the number and time cost of download client session RPC requests?
        # Premature optimization?

        download_clients = self.free_space_download_clients()
        if not download_clients:
            return None

        results = {}

        logger.info(
            "Deleting download items no longer registered with tracker to free space",
        )
        # If there are items to delete, then after deleting each item, refresh the
        # download client free space and list of download items and repeat until either
        # there are no more download items to delete or the download client has
        # sufficient free space.
        download_clients = self.free_space_remove_items(
            download_clients,
            results,
            "find_unregistered",
        )
        if not download_clients:
            return results

        logger.info(
            "Deleting orphaned files not belonging to any download item to free space",
        )
        for orphan_download_clients, file_path, file_stat in self.find_orphans():
            first_download_client = next(orphan_download_clients.values())
            first_download_client.delete_files((file_path, file_stat))
            results.setdefault(
                first_download_client.config["url"],
                [],
            ).append(str(file_path))
            # Refresh the sessions data including free space
            for download_client in orphan_download_clients.values():
                download_client.get_session()
            # Do any download clients still need to free space?
            download_clients = self.free_space_download_clients()
            if not download_clients:
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
                    download_client.min_free_space
                    - download_client.client.session.download_dir_free_space,
                ),
            )
            kwargs = dict(speed_limit_down=0, speed_limit_down_enabled=True)
            # TODO: Notification when downloading is paused
            logger.info("Stopping downloading: %s", kwargs)
            download_client.client.set_session(**kwargs)

        return results

    def free_space_download_clients(self):
        """
        Return all download clients that don't have sufficient free space.
        """
        return {
            download_client_url: download_client
            for download_client_url, download_client in self.download_clients.items()
            if not download_client.free_space_maybe_resume()
        }

    def free_space_remove_items(
        self,
        download_clients,
        results,
        download_client_method="find_seeding",
    ):
        """
        Delete download items until sufficient space is free the items are exhausted.

        If there are items to delete, then after deleting each item, refresh the
        download clients free space and lists of download items and repeat until either
        there are no more download items to delete or all download clients have
        sufficient free space.
        """
        while download_clients:
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
                    ).append(repr(download_item))
                    download_clients = self.free_space_download_clients()
                    break
                if removed_size:
                    break
            else:
                break
        return download_clients

    def find_orphans(self):
        """
        Find paths in download client directories that don't correspond to an item.

        Iterate through all the paths managed by each download client in turn, check
        all paths within those directories against the download items known to the
        download client, and report all paths that are unknown to the download client.

        Useful to identify paths to delete when freeing disk space.  Returned sorted
        from paths that use the least disk space to the most.
        """
        # Collect all the download item files that actually exist currently
        item_files = set()
        for download_client_url, download_client in self.download_clients.items():
            for download_item in download_client.items:
                item_files.update(download_item.list_files(selected=False))

        # Aggregate all the download item directories across all download clients.  Some
        # download item directories may be shared across download clients and some may
        # be on different filesystems so we need to aggregate them all across download
        # clients but keep track of which download clients use which directories.
        download_item_dirs = {}
        for download_client_url, download_client in self.download_clients.items():
            for servarr_download_client in download_client.servarrs.values():
                for (
                    download_item_dir
                ) in servarr_download_client.download_item_dirs.values():
                    download_item_dirs.setdefault(download_item_dir, {})[
                        download_client_url
                    ] = download_client

        # Collect any files in any download item directories that aren't download item
        # files.  Also yield the download clients that the file's download item
        # directory use.  Also yield the `stat` syscall results for that file to reduce
        # such syscalls downstream.
        orphans = []
        for download_item_dir, download_clients in download_item_dirs.items():
            first_download_client = next(iter(download_clients.values()))
            for dirpath, _, filenames in os.walk(download_item_dir):
                for filename in filenames:
                    file_path = download_item_dir / dirpath / filename
                    if (
                            file_path not in item_files
                            and not {
                                suffix for suffix in first_download_client.FILE_SUFFIXES
                                if file_path.name.endswith(suffix)
                            }
                    ):
                        orphans.append(
                            (download_clients, file_path, file_path.stat()),
                        )

        # Order orphans by smallest size first.  Use this sort order to give the user as
        # long as possible to rescue any larger, and thus harder to restore, files.
        # Also cleans up noisy small file clutter first.
        orphans.sort(key=lambda orphan: orphan[2].st_size)

        return orphans
