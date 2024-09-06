# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Download item metadata operations used in Prunerr configuration.

Used to determine item indexer priority, reviewing grabbed items, etc.
"""

import typing
import re
import logging

import jinja2.environment
import jinja2.nativetypes

from . import downloaditem

logger = logging.getLogger(__name__)

jinja_env = jinja2.nativetypes.NativeEnvironment()

CONFIG_ITEM_KEY = "item"
CONFIG_EQUAL_KEY = "equals"
CONFIG_MINIMUM_KEY = "minimum"
CONFIG_MAXIMUM_KEY = "maximum"
CONFIG_PRIORITIES_KEY = "priorities"
CONFIG_HOSTNAMES_KEY = "hostnames"
CONFIG_AGGREGATION_PORTION = "portion"


def parse_operation(operation_config: dict) -> dict:
    """
    Parse or compile any expressions in the configuration.

    Done for better speed when executing the same operation against multiple download
    items.

    :param operation_config: The operation configuration from the Prunerr configuration.
    :return: The operation configuration augmented with any pre-processing possible.
    :raises NotImplementedError: The operation configuration YAML has a problem.
    """
    if CONFIG_EQUAL_KEY in operation_config and (
        CONFIG_MINIMUM_KEY in operation_config or CONFIG_MAXIMUM_KEY in operation_config
    ):
        raise NotImplementedError(
            f"Operation {operation_config['type']!r} "
            f"includes both `equals` and `minimum` or `maximum`"
        )
    operation_config.update(
        (key, jinja_env.from_string(operation_config[key]))
        for key in (
            "template",
            CONFIG_ITEM_KEY,
            CONFIG_EQUAL_KEY,
            CONFIG_MINIMUM_KEY,
            CONFIG_MAXIMUM_KEY,
        )
        if key in operation_config and isinstance(operation_config[key], str)
    )

    for child_operation_config in operation_config.get("operations", []):
        parse_operation(child_operation_config)

    return operation_config


def render_value(
    template: typing.Optional[jinja2.environment.Template],
    **context,
) -> typing.Any:
    """
    Render a Jinja template string, or return directly if not a string.

    :param template: The scalar YAML value or compiled Jinja template.
    :param context: A mapping of what is available when rendering the template.
    :return: The scalar YAML value or rendered template output.
    """
    if isinstance(template, jinja2.environment.Template):
        return template.render(**context)
    return template


class PrunerrOperationsContext:
    """
    Execute multiple operations for the same context.
    """

    def __init__(self, operations: "PrunerrOperations", **context):
        """
        Capture references to the operations and the template context.
        """
        self.operations = operations
        self.context = context

    def exec_operations(self, operation_configs: list) -> tuple:
        """
        Execute each of the configured indexer priority operations.

        :param operation_configs: The operation configurations from the Prunerr
            configuration.
        :return: Whether this download item should be included when filtering items and
            the values by which to sort download items.
        :raises NotImplementedError: The operation configuration is invalid.
        """
        # TODO: Add `name` to operation configs and use in log/exc messages
        sort_key: list = []
        include = True
        for operation_config in operation_configs:
            executor = getattr(self, f"exec_operation_{operation_config['type']}", None)
            if executor is None:
                raise NotImplementedError(
                    f"No indexer priority operation executor found for type "
                    f"{operation_config['type']!r}"
                )
            # Delegate to the executor to get the operation value for this download item
            if (sort_value := executor(operation_config)) is None or isinstance(
                sort_value, jinja2.runtime.Undefined
            ):
                # If an executor returns None, all other handling should be skipped
                return include, tuple(sort_key)
            include, sort_value = self.apply_sort_value(
                operation_config,
                include,
                sort_value,
            )
            sort_key.append(sort_value)
        return include, tuple(sort_key)

    def exec_operation_value(  # noqa: V105
        self,
        operation_config: dict,
    ) -> typing.Any:
        """
        Render the template or return the YAML scalar value.

        :param operation_config: The operation configuration from the Prunerr
            configuration.
        :return: The scalar YAML value or rendered template output.
        """
        return render_value(operation_config["template"], **self.context)

    def exec_operation_or(  # noqa: V105
        self,
        operation_config: dict,
    ) -> typing.Any:
        """
        Return `True` if any of the nested operations return `True`.

        :param operation_config: The operation configuration from the Prunerr
            configuration.
        :return: The value of the nested operations if any are `True`.
        """
        _, sort_key = self.exec_operations(
            operation_config["operations"],
        )
        for sort_value in sort_key:
            if sort_value:
                return sort_value
        return sort_key[-1] if sort_key else False

    def exec_operation_and(  # noqa: V105
        self,
        operation_config: dict,
    ) -> typing.Any:
        """
        Return `False` if any of the nested operations return `False`.

        :param operation_config: The operation configuration from the Prunerr
            configuration.
        :return: The value of the nested operations if all are `True`.
        """
        _, sort_key = self.exec_operations(
            operation_config["operations"],
        )
        for sort_value in sort_key:
            if not sort_value:
                return sort_value
        return sort_key[-1]

    def exec_operation_files(  # noqa: V105
        self,
        operation_config: dict,
    ) -> typing.Any:
        """
        Return aggregated values from item files.

        :param operation_config: The operation configuration from the Prunerr
            configuration.
        :return: The aggregated value.
        :raises NotImplementedError: The operation configuration is invalid.
        """
        template = operation_config.get("template")
        aggregation = operation_config.get("aggregation")
        if aggregation not in {None, CONFIG_AGGREGATION_PORTION}:
            raise NotImplementedError(f"Unknown item files aggregation {aggregation!r}")

        if CONFIG_ITEM_KEY in operation_config:
            item = render_value(  # pragma: no cover
                operation_config[CONFIG_ITEM_KEY],
                **self.context,
            )
        elif CONFIG_ITEM_KEY in self.context:
            item = self.context[CONFIG_ITEM_KEY]
        else:
            raise NotImplementedError(  # pragma: no cover
                f"Missing download item template in ``item``: {operation_config!r}",
            )
        if not item.files:
            if item.hashString.upper() not in self.operations.seen_empty_files:
                logger.debug(
                    "Download item contains no files: %r",
                    item,
                )
                self.operations.seen_empty_files.add(item.hashString.upper())
            return False

        wanted_files, matching_files = filter_item_files(operation_config, item)
        sort_value = (
            sum(template.render(file=matching_file) for matching_file in matching_files)
            if template
            else len(matching_files)
        )

        if aggregation == CONFIG_AGGREGATION_PORTION:
            if template:
                total = sum(
                    template.render(file=wanted_file) for wanted_file in wanted_files
                )
            else:
                total = len(wanted_files)  # pragma: no cover
            sort_value = 0 if not total else sort_value / total

        return sort_value

    def apply_sort_value(
        self,
        operation_config: dict,
        include: bool,
        sort_value: typing.Any,
    ) -> tuple:
        """
        Apply any restrictions that can apply across different operation types.

        :param operation_config: The operation configuration from the Prunerr
            configuration.
        :param include: Whether this download item should be included when filtering
            items.
        :param sort_value: The values by which to sort download items.
        :return: The applied ``include`` and ``sort_value`` per the
            ``operation_config``.
        :raises NotImplementedError: The resulting sort value is not supported.
        """
        sort_bool = None
        if CONFIG_EQUAL_KEY in operation_config:
            sort_bool = sort_value == render_value(
                operation_config[CONFIG_EQUAL_KEY],
                **self.context,
            )
        else:
            if CONFIG_MINIMUM_KEY in operation_config:
                sort_bool = sort_value >= render_value(
                    operation_config[CONFIG_MINIMUM_KEY],
                    **self.context,
                )
            if CONFIG_MAXIMUM_KEY in operation_config and (
                sort_bool is None or sort_bool
            ):
                sort_bool = sort_value <= render_value(
                    operation_config[CONFIG_MAXIMUM_KEY],
                    **self.context,
                )
        if sort_bool is not None:
            sort_value = sort_bool
        # Should the operation value be used to filter this download item?
        if operation_config.get("filter", False) and include:
            include = bool(sort_value)
        # Should the operation value be reversed when ordering the download items?
        if operation_config.get("reversed", False):
            if isinstance(sort_value, (bool, int, float)):
                sort_value = 0 - sort_value
            elif isinstance(sort_value, (tuple, list, str)):
                sort_value = reversed(sort_value)
            else:
                raise NotImplementedError(
                    f"Indexer priority operation value doesn't support `reversed`:"
                    f"{sort_value!r}"
                )

        return include, sort_value


def filter_item_files(
    operation_config: dict,
    item: downloaditem.PrunerrDownloadItem,
) -> tuple:
    """
    Filter download item files are per the configuration.

    :param operation_config: The operation configuration from the Prunerr
        configuration.
    :param item: The download item whose files to filter.
    :return: The files selected for download and which of those files passed
        filtering.
    """
    filter_attrs = operation_config.get("filter-attrs", [])
    path_patterns = operation_config.get("path-patterns", [])
    wanted_files = matching_files = [
        item_file
        for item_file in item.files
        if item_file.selected and item_file.path.exists()
    ]
    for filter_attr in filter_attrs:
        matching_files = [
            matching_file
            for matching_file in matching_files
            if getattr(matching_file, filter_attr)
        ]
    if path_patterns:
        pattern_files: list = []
        for pattern in path_patterns:
            pattern_files.extend(
                matching_file
                for matching_file in matching_files
                if re.fullmatch(pattern, matching_file.name)
            )
        matching_files = pattern_files
    return wanted_files, matching_files


class PrunerrOperations:
    """
    Download item metadata operations used in Prunerr configuration.

    Used to determine item indexer priority, reviewing grabbed items, etc.
    """

    CONTEXT_FACTORY = PrunerrOperationsContext

    def __init__(self, download_client, config):
        """
        Capture references to the download client and operations configuration.
        """
        self.download_client = download_client
        self.config = config

        if CONFIG_PRIORITIES_KEY not in config:
            # Load sample Prunerr config file and use for default "priorities" config:
            config[CONFIG_PRIORITIES_KEY] = [
                self.download_client.runner.example_confg["indexers"][
                    CONFIG_PRIORITIES_KEY
                ][-1]
            ]
        self.indexer_operations = self.parse()

        self.seen_empty_files = set()

    def parse(self) -> dict:
        """
        Recursively parse or compile any expressions in the configurations.

        :return: The compiled operation configurations.
        """
        indexer_operations: dict = {}
        for operations_type, indexer_configs in self.config.items():
            if operations_type == CONFIG_HOSTNAMES_KEY:
                continue
            indexer_operations[operations_type] = {}
            for indexer_config in indexer_configs:
                indexer_operations[operations_type][
                    indexer_config["name"]
                ] = indexer_config
                for operation_config in indexer_config["operations"]:
                    parse_operation(operation_config)
        return indexer_operations

    def exec_indexer_operations(
        self,
        item: downloaditem.PrunerrDownloadItem,
        operations_type: str = CONFIG_PRIORITIES_KEY,
        **context,
    ) -> tuple:
        """
        Run operations for the download item, cache, and return results.

        :param item: The download item to which to apply the operation.
        :param operations_type: The key in the Prunerr configuration that contains the
            operations configurations.
        :param context: A mapping of what is available when rendering templates.
        :return: Whether this download item should be included when filtering items and
            the values by which to sort download items.
        """
        cached_results = dict(vars(item)).setdefault("prunerr_operations_results", {})
        if operations_type in cached_results:
            return cached_results[operations_type]  # pragma: no cover

        indexer_configs = self.indexer_operations.get(operations_type, {})
        if (indexer_name := item.match_indexer_urls()) not in indexer_configs:
            indexer_name = None
        indexer_idx = list(indexer_configs.keys()).index(indexer_name)
        indexer_config = indexer_configs[indexer_name]

        include, sort_key = self.CONTEXT_FACTORY(
            self,
            item=item,
            **context,
        ).exec_operations(indexer_config["operations"])
        cached_results[operations_type] = (include, (indexer_idx,) + sort_key)
        return cached_results[operations_type]
