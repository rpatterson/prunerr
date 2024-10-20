# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Run Prunerr commands across multiple Servarr instances and download clients.
"""

import os
import collections.abc
import typing
import time
import datetime
import pathlib
import logging

import yaml
import tenacity

import prunerr.downloadclient
import prunerr.downloaditem
import prunerr.servarr
from . import utils
from .utils import cached_property
from .commands import export
from . import operations

logger = logging.getLogger(__name__)


class PrunerrRunner(utils.PrunerrComponent):
    """
    Run Prunerr sub-commands across multiple Servarr instances and download clients.
    """

    EXAMPLE_CONFIG = pathlib.Path(__file__).parent / "home" / ".config" / "prunerr.yml"
    DEFAULTS_CONFIG = EXAMPLE_CONFIG.with_name(
        f"{EXAMPLE_CONFIG.stem}-defaults{EXAMPLE_CONFIG.suffix}",
    )
    CONFIG_SERVARRS_KEY = "servarrs"
    CONFIG_DOWNLOAD_CLIENTS_KEY = "download-clients"
    CONFIG_INDEXERS_KEY = "indexers"
    CONFIG_INDEXERS_CONFIG_KEY = "indexers-config"
    CONFIG_NO_DEFAULTS = (
        CONFIG_SERVARRS_KEY,
        CONFIG_DOWNLOAD_CLIENTS_KEY,
        CONFIG_INDEXERS_KEY,
    )

    config_stat: os.stat_result
    quiet = False

    def __init__(self, config):
        """
        Capture a reference to the global Prunerr configuration file.
        """
        with self.EXAMPLE_CONFIG.open() as config_opened:
            self.example_config = yaml.safe_load(config_opened)
        with self.DEFAULTS_CONFIG.open() as defaults_opened:
            self.example_config.update(yaml.safe_load(defaults_opened))
        self.config_file = pathlib.Path(config)

        # Initialize any local instance state
        self.download_clients = {}
        self.servarrs = {}

    @cached_property
    def config(self) -> dict:
        """
        Parse and validate the configuration file and cache in instance state.

        :return: The parsed YAML configuration as a Python mapping
        """
        return self.validate()

    def validate(self) -> dict:
        """
        Parse the configuration file and raise meaningful errors for improper values.

        :return: The parsed YAML configuration as a Python mapping
        :raises utils.PrunerrValidationError: The YAML configuration file has a problem
        """
        # Refresh the Prunerr configuration from the file
        if not self.config_file.is_file():
            raise utils.PrunerrValidationError(
                f"Configuration file not found: {self.config_file}"
            )
        self.config_stat = self.config_file.stat()
        with self.config_file.open(encoding="utf-8") as config_opened:
            config = yaml.safe_load(config_opened)

        # Avoid issues with empty keys having a `None` value in YAML:
        for top_key in self.example_config.keys():
            if top_key in config and config[top_key] is None:
                logger.debug(
                    "Top-level configuration key is empty: %s",
                    top_key,
                )
                config[top_key] = {}

        # Raise helpful errors for required values:
        if not config.get("download-clients"):
            raise utils.PrunerrValidationError(
                "Configuration file must include at least one download client"
                f" configuration under  `download-clients`: {self.config_file}"
            )

        # Pull defaults from the example configuration:
        for top_key, top_config in self.example_config.items():
            if top_key not in self.CONFIG_NO_DEFAULTS:
                config.setdefault(top_key, top_config)
        config["daemon"].setdefault("poll", self.example_config["daemon"]["poll"])

        # Render derived indexer values:
        indexers_config = config[self.CONFIG_INDEXERS_CONFIG_KEY] = {
            indexers_key: operations.jinja_env.from_string(indexers_template)
            for indexers_key, indexers_template in config.get(
                self.CONFIG_INDEXERS_CONFIG_KEY, {}
            ).items()
        }
        for indexer_name, indexer in config.setdefault(
            self.CONFIG_INDEXERS_KEY,
            {},
        ).items():
            indexer_config = indexer.setdefault("config", {})
            indexer_config.setdefault("name", indexer_name)
            for indexers_key, indexers_template in indexers_config.items():
                indexer_config[indexers_key] = indexers_template.render(
                    indexer_config=indexer_config,
                )

        # Compile Jinja templates:
        config["stages"] = prunerr.operations.parse(
            config["stages"],
            self.example_config["stages"],
        )

        return config

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(utils.RETRY_EXC_TYPES),
        # Match the default daemon poll wait. It might be better to take this value from
        # the user's configuration file, but we shouldn't parse YAML at import-time and
        # it's not worth refactoring and the trade off in simplicity to use `tenacity`
        # at run-time:
        wait=tenacity.wait_fixed(60),
        reraise=True,
        before_sleep=tenacity.before_sleep_log(logger, logging.WARNING),
    )
    def update(self) -> dict:
        """
        Connect to the download and Servarr clients, waiting for reconnection on error.

        Aggregate all download clients from all Servarr instances defined in the config.

        :return: Map download client URLs to
            ``prunerr.downloadclient.PrunerrDownloadClient`` instances
        """
        super().update()

        # Update Servarr API clients
        servarrs = {}
        for servarr_name, servarr_config in self.config.get("servarrs", {}).items():
            servarr_config.setdefault("name", servarr_name)
            servarrs[utils.normalize_url(servarr_config["url"])] = (
                prunerr.servarr.PrunerrServarrInstance(self)
            )
            servarrs[servarr_config["url"]].update(servarr_config)
        self.servarrs = servarrs

        # Collate the download client configurations that may not be attached to a
        # Servarr instance:
        download_client_configs = {}
        for download_client_name, download_client_config in self.config[
            "download-clients"
        ].items():
            download_client_config.setdefault("name", download_client_name)
            download_client_config.update(
                prunerr.downloadclient.config_from_url(download_client_config["url"]),
            )
            download_client_configs[download_client_config["url"]] = (
                download_client_config
            )
        # Merge in download clients defined in Servarr settings that aren't also defined
        # under the top-level `download-clients` key:
        for servarr in self.servarrs.values():
            for (
                download_client_url,
                servarr_download_client,
            ) in servarr.download_clients.items():
                download_client_config = download_client_configs.get(
                    download_client_url,
                )
                # The configuration from `download-clients` takes precedence over the
                # Servarr settings, but a download client may be defined *only* in the
                # Servarr settings:
                if download_client_config is None:
                    download_client_config = prunerr.downloadclient.config_from_url(
                        download_client_url,
                    )
                    download_client_config["name"] = servarr_download_client.config[
                        "name"
                    ]
                    download_client_configs[download_client_url] = (
                        download_client_config
                    )
                # Identify which download client directories are used as queues for
                # which Servarr instances:
                download_client_config.setdefault("servarrs", {}).setdefault(
                    servarr_download_client.download_dir,
                    servarr_download_client,
                )

        # Update the download clients, instantiating if newly defined
        download_clients: dict = {}
        for (
            download_client_url,
            download_client_config,
        ) in download_client_configs.items():
            download_client = (
                # Preserve any cached state in existing download clients
                self.download_clients[download_client_url]
                if download_client_url in self.download_clients
                # Instantiate newly defined download clients
                else prunerr.downloadclient.PrunerrDownloadClient(self)
            )
            download_clients[download_client_url] = download_client
            # Associate with Servarr instances
            for servarr_download_client in download_client_config.get(
                "servarrs",
                {},
            ).values():
                servarr_download_client.download_client = download_client
            download_client.update(download_client_config)
        self.download_clients = download_clients

        return self.download_clients

    # Sub-commands

    def apply_(
        self,
        stages: collections.abc.Iterable = operations.STAGES_DEFAULT,
    ) -> typing.Optional[dict]:
        """
        Apply configured operations for the stages to all download clients.

        :param stages: The download item life-cycle stages whose operations to apply.
        :return: Map stages to download client URLs to the results of any actions taken.
        :raises ValueError: Something is wrong with the arguments.
        """
        if invalid_stages := set(stages).difference(self.config["stages"]):
            raise ValueError(  # pragma: no cover
                "Some passed stages are not in the configuration: "
                f"{list(invalid_stages)!r}",
            )
        apply_results = {}
        # Let the YAML order determine the order the stages are applied in:
        for stage in self.example_config["stages"]:
            if stage not in stages:
                continue

            if stage_results := self.apply_stage(stage):
                apply_results[stage] = stage_results

        if apply_results:
            return apply_results
        return None

    def export(self) -> typing.Optional[dict]:
        """
        Link imported files back into download items and verify, Servarr import inverse.

        :return: Map download client items to any files have been linked.
        """
        export_results = {}

        # The Servarr instances drive the export process:
        for servarr_url, servarr in self.servarrs.items():
            command_run = export.ExportCommandRun(servarr)
            command_run.update()
            if servarr_export_results := command_run():
                export_results[servarr_url] = servarr_export_results

        # Report results if any:
        if export_results:
            return export_results
        return None

    def daemon(
        self,
        stages: collections.abc.Iterable = operations.STAGES_DEFAULT,
    ):
        """
        Prune download client items continuously.

        :param stages: The download item life-cycle stages whose operations to apply.
        """
        # Log only once at the start messages that would be noisy if repeated for every
        # daemon poll loop.
        self.quiet = False
        while True:  # pylint: disable=while-used
            # Start the clock for the poll loop as early as possible to keep the inner
            # loop duration as accurate as possible.
            start = time.time()

            try:
                self._daemon_inner(stages)
            except utils.RETRY_EXC_TYPES as exc:
                # TODO: If `ValueError`, check if it's from `transmission_rpc` and
                # related to an interrupted RPC response, otherwise re-raise.
                logger.warning(  # pragma: no cover
                    "Connection error while updating from server: %s",
                    exc,
                )
                # Re-connect to external services and retry
            else:
                # Don't repeat noisy messages from now on.
                self.quiet = True
            logger.debug("Sub-command `apply` completed in %ss", time.time() - start)

            # Determine the poll interval before clearing the config
            poll = self.config["daemon"]["poll"]

            # Wait for the next interval. Note that polling is required because there is
            # no event we can subscribe to that reliably determines disk space margin
            # *as* the download clients are downloading:
            if (time_left := poll - (time.time() - start)) > 0:
                time.sleep(time_left)
            logger.debug("Sub-command `daemon` looping after %ss", time.time() - start)

    # Methods to list the download items in each life-cycle stage:

    def filter_orphans(self) -> collections.abc.Generator:  # noqa: V105
        """
        Find paths in download client directories that don't correspond to an item.

        Iterate through all the paths managed by each download client in turn, check
        all paths within those directories against the download items known to the
        download client, and report all paths that are unknown to the download client.

        Useful to identify paths to delete when freeing disk space.  Returned sorted
        from paths that use the least disk space to the most.

        :return: The orphaned filesystem paths.
        """
        item_files: set = set()
        download_item_dirs: dict = {}
        for download_client in self.download_clients.values():

            # Collect all the download item files that actually exist currently
            for download_item in download_client.items:
                item_files.update(
                    item_file.path
                    for item_file in download_item.files
                    if item_file.selected and item_file.exists
                    # Avoid deleting incomplete files for newly added torrents. Exclude
                    # files whose creation date is newer than when the download items
                    # were requested from the RPC API:
                    and datetime.datetime.fromtimestamp(
                        item_file.stat.st_ctime,
                        datetime.timezone.utc,
                    )
                    < download_client.items_requested
                )
                item_files.add(download_item.log_path)

            # Aggregate all the download item directories across all download clients.
            # Some download item directories may be shared across download clients and
            # some may be on different filesystems so we need to aggregate them all
            # across download clients:
            download_item_dirs.setdefault(download_client.download_dir, None)
            download_item_dirs.setdefault(download_client.seeding_dir, None)
            if download_client.session["incomplete-dir-enabled"]:  # pragma: no cover
                download_item_dirs.setdefault(
                    pathlib.Path(download_client.session["incomplete-dir"]),
                    None,
                )

        # Collect any files in any download item directories that aren't download item
        # files.  Also yield the download clients that the file's download item
        # directory use.  Also yield the `stat` syscall results for that file to reduce
        # such syscalls downstream.
        for download_item_dir in download_item_dirs:
            for dirpath, _, filenames in os.walk(download_item_dir):
                for filename in filenames:
                    file_path = download_item_dir / dirpath / filename
                    if file_path not in item_files:
                        yield file_path

    def apply_remove(  # noqa: V105
        self,
        operation: operations.PrunerrOperation,
        item: pathlib.Path,
        **context,  # pylint: disable=unused-argument
    ) -> dict:
        """
        Remove this filesystem path according to the operation configuration.

        :param operation: The operation configuration from the configuration file YAML.
        :param context: Additional names and values available in templates.
        :param item: The filesystem path to remove.
        :return: A mapping describing the details of removal.
        """
        remove_result = {
            operations.ACTION_REMOVE: operation.config[operations.ACTION_REMOVE]
        }
        stat = item.stat()
        size = (stat.st_blocks * 512) if (stat.st_nlink == 1) else 0
        logger.info(
            "Deleting for %(operation)r: %(item)r -> %(size)s",
            {
                "operation": operation,
                "item": str(item),
                "size": utils.format_size(size),
            },
        )
        self.delete_path(item)

        for download_client in self.download_clients.values():
            download_client.client.get_session()

        return remove_result

    # Other methods:

    def apply_stage(
        self,
        stage: str = prunerr.operations.STAGE_QUEUED,
    ) -> typing.Optional[dict]:
        """
        Apply configured operations for a life-cycle stage to all download client items.

        :param stage: The download item life-cycle stage whose operations to apply.
        :return: Map download client URLs to download item hash IDs to mappings
            describing the actions taken if any.
        """
        if getattr(self, f"filter_{stage.replace('-', '_')}", None) is None:
            stage_results = {}
            for download_client in self.download_clients.values():
                prunerr_stage = prunerr.operations.PrunerrStage(
                    stage,
                    self.config["stages"][stage],
                    download_client,
                )
                if applier_results := prunerr_stage():
                    stage_results[download_client.config["url"]] = applier_results
        else:
            prunerr_stage = prunerr.operations.PrunerrStage(
                stage,
                self.config["stages"][stage],
                self,
            )
            stage_results = prunerr_stage()
        return stage_results

    def _daemon_inner(
        self,
        stages: collections.abc.Iterable = operations.STAGES_DEFAULT,
    ):
        """
        Prune download client items continuously.

        :param stages: The download item life-cycle stages whose operations to apply.
        """
        # Refresh the list of download items
        self.update()
        # Run the `apply` sub-command as the inner loop
        return self.apply_(stages)

    @cached_property
    def managed_dirs(self) -> list:
        """
        Determine which directories are the top-level ancestors of files and items.

        Used to determine how far "up" the chain of ancestors to delete empty
        directories when deleting items or orphans.

        :return: The filesystem paths for the directories from deepest or most specific
            to the top-level download client's ``downloadDir`` and it's siblings.
        """
        managed_dirs = []
        for servarr in self.servarrs.values():
            for servarr_download_client in servarr.download_clients.values():
                managed_dirs.append(servarr_download_client.download_dir)
                managed_dirs.append(servarr_download_client.seeding_dir)
        for download_client in self.download_clients.values():
            managed_dirs.append(download_client.download_dir)
            managed_dirs.append(download_client.seeding_dir)
            if download_client.incomplete_dir is not None:
                managed_dirs.append(download_client.incomplete_dir)
            else:
                pass  # pragma: no cover
        return managed_dirs

    def delete_path(self, path: pathlib.Path) -> list:
        """
        Delete this file or directory and empty parent directories.

        :param path: The filesystem path to a file to delete or a directory to
            recursively delete.
        :return: The filesystem paths for all parent directories that were also deleted.
        :raises ValueError: The given ``path`` is not valid to delete.
        """
        # The path is not in one of our managed directories, this should never happen:
        for managed_dir in self.managed_dirs:
            if managed_dir in path.parents:
                break
        else:
            raise ValueError(  # pragma: no cover
                "Refusing to delete a path in an un-managed directory",
            )

        # Delete the given path:
        if path.exists():
            path.unlink()
        else:
            # Under high download client load, the deletion from the client
            # sometimes seems to fail but Prunerr successfully deletes the data. On
            # the next `daemon` loop Prunerr will try to delete it from the client
            # again, which is correct, but then chokes on the missing files it
            # already deleted.
            logger.warning(
                "Path to be deleted doesn't exist: %s",
                path,
            )

        # Also remove the ancestor directories if they're not empty:
        removed_parents = []
        for relative_parent in path.relative_to(managed_dir).parents[:-1]:
            parent = managed_dir / relative_parent
            if parent.exists():
                if next(parent.iterdir(), None) is not None:
                    # Not empty, stop removing parents:
                    break
                parent.rmdir()
                removed_parents.append(parent)
            else:
                pass  # pragma: no cover
        return removed_parents
