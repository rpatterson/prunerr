"""
Download item metadata operations used in Prunerr configuration.

Used to determine item indexer priority, reviewing grabbed items, etc.
"""

import re
import logging

logger = logging.getLogger(__name__)

missing_value = object()


class PrunerrOperations:
    """
    Download item metadata operations used in Prunerr configuration.

    Used to determine item indexer priority, reviewing grabbed items, etc.
    """

    def __init__(self, download_client, config):
        """
        Capture a references to the download client and operations configuration.
        """
        self.download_client = download_client
        self.config = config

        if "priorities" not in config:
            # Load sample Prunerr config file and use for default "priorities" config
            config["priorities"] = [
                self.download_client.runner.example_confg["indexers"]["priorities"][-1]
            ]
        self.indexer_operations = {
            operations_type: {
                indexer_config["name"]: indexer_config
                for indexer_config in indexer_configs
            }
            for operations_type, indexer_configs in config.items()
            if operations_type != "hostnames"
        }

        self.seen_empty_files = set()

    def exec_indexer_operations(self, item, operations_type="priorities"):
        """
        Run indexer operations for the download item and return results.
        """
        cached_results = vars(item).setdefault("prunerr_operations_results", {})
        if operations_type in cached_results:
            return cached_results[operations_type]

        indexer_configs = self.indexer_operations.get(operations_type, {})
        indexer_name = item.match_indexer_urls()
        if indexer_name not in indexer_configs:
            indexer_name = None
        indexer_idx = list(indexer_configs.keys()).index(indexer_name)
        indexer_config = indexer_configs[indexer_name]

        include, sort_key = self.exec_operations(indexer_config["operations"], item)
        cached_results[operations_type] = (include, (indexer_idx,) + sort_key)
        return cached_results[operations_type]

    def exec_operations(self, operation_configs, item):
        """
        Execute each of the configured indexer priority operations.
        """
        # TODO: Add `name` to operation configs and use in log/exc messages
        sort_key = []
        include = True
        for operation_config in operation_configs:
            executor = getattr(self, f"exec_operation_{operation_config['type']}", None)
            if executor is None:
                raise NotImplementedError(
                    f"No indexer priority operation executor found for type "
                    f"{operation_config['type']!r}"
                )
            # Delegate to the executor to get the operation value for this download item
            sort_value = executor(operation_config, item)
            if sort_value is None:
                # If an executor returns None, all other handling should be skipped
                return include, tuple(sort_key)
            include, sort_value = self.apply_sort_value(
                operation_config,
                include,
                sort_value,
            )
            sort_key.append(sort_value)
        return include, tuple(sort_key)

    def apply_sort_value(self, operation_config, include, sort_value):
        """
        Apply any restrictions that can apply across different operation types.
        """
        sort_bool = None
        if "equals" in operation_config:
            sort_bool = sort_value == operation_config["equals"]
            if "minimum" in operation_config or "maximum" in operation_config:
                raise ValueError(
                    f"Operation {operation_config['type']!r} "
                    f"includes both `equals` and `minimum` or `maximum`"
                )
        else:
            if "minimum" in operation_config:
                sort_bool = sort_value >= operation_config["minimum"]
            if "maximum" in operation_config and (sort_bool is None or sort_bool):
                sort_bool = sort_value <= operation_config["maximum"]
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

    def exec_operation_value(self, operation_config, item):  # noqa: V105
        """
        Return the attribute or key value for the download item.
        """
        # Use `missing_value` instead of `hasattr()`
        # to avoid redundant property method calls
        value = getattr(item, operation_config["name"], missing_value)
        if value is not missing_value:
            return value
        return None

    def exec_operation_or(self, operation_config, item):  # noqa: V105
        """
        Return `True` if any of the nested operations return `True`.
        """
        _, sort_key = self.exec_operations(
            operation_config["operations"],
            item,
        )
        for sort_value in sort_key:
            if sort_value:
                return sort_value
        return sort_key[-1] if sort_key else False

    def exec_operation_and(self, operation_config, download_item):  # noqa: V105
        """
        Return `False` if any of the nested operations return `False`.
        """
        _, sort_key = self.exec_operations(
            operation_config["operations"],
            download_item,
        )
        for sort_value in sort_key:
            if not sort_value:
                return sort_value
        return sort_key[-1]

    def exec_operation_files(self, operation_config, download_item):  # noqa: V105
        """
        Return aggregated values from item files.
        """
        file_attr = operation_config.get("name", "size")
        aggregation = operation_config.get("aggregation", "portion")
        total = operation_config.get("total", "size_when_done")

        if not download_item.files:
            if download_item.hashString.upper() not in self.seen_empty_files:
                logger.debug(
                    "Download item contains no files: %r",
                    download_item,
                )
                self.seen_empty_files.add(download_item.hashString.upper())
            return False

        patterns = operation_config.get("patterns", [])
        if patterns:
            matching_files = []
            for pattern in patterns:
                matching_files.extend(
                    item_file
                    for item_file in download_item.files
                    if re.fullmatch(pattern, item_file.name)
                )
        else:
            matching_files = download_item.files

        if aggregation == "count":
            sort_value = len(matching_files)
        elif aggregation in {"sum", "portion"}:
            sort_value = sum(
                getattr(matching_file, file_attr) for matching_file in matching_files
            )
            if aggregation == "portion":
                sort_value = sort_value / getattr(download_item, total)
        else:
            raise ValueError(f"Unknown item files aggregation {aggregation!r}")

        return sort_value
