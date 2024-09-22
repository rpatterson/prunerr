# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Operations from the configuration applied to download items during life-cycle stages.
"""

import typing
import functools
import pathlib
import re
import logging

import jinja2.environment
import jinja2.nativetypes

from . import utils
from .utils import cached_property

root_logger = logging.getLogger()
logger = logging.getLogger(__name__)

STAGE_QUEUED = "queued"
STAGE_UPGRADED = "upgraded"
STAGE_SEEDING = "seeding"
STAGE_ALL = "all"
STAGE_FREE_SPACE = "free-space"
STAGE_ORPHANS = "orphans"
STAGES_DEFAULT = (
    STAGE_QUEUED,
    STAGE_UPGRADED,
    STAGE_SEEDING,
    STAGE_ALL,
    STAGE_FREE_SPACE,
)
STAGES = STAGES_DEFAULT + (STAGE_ORPHANS,)
STAGES_SET = set(STAGES)
OPERATION_INCLUDE = "include"
OPERATION_SORT = "sort"
OPERATION_BREAK = "break"
ACTION_REMOVE = "remove"
ACTION_BLACKLIST = "blacklist"
ACTION_CHANGE = "change"
ACTION_MOVE = "move"
ACTION_VERIFY = "verify"
ACTION_LOG = "log"
ACTION_ARGS = "args"
ACTIONS = {ACTION_REMOVE, ACTION_CHANGE, ACTION_MOVE, ACTION_VERIFY, ACTION_LOG}
TEMPLATE_KEYS = (
    OPERATION_INCLUDE,
    OPERATION_SORT,
    OPERATION_BREAK,
    ACTION_MOVE,
    ACTION_LOG,
    ACTION_ARGS,
)
CONTINUE_EXC_TYPES = utils.RETRY_EXC_TYPES + (OSError,)


def parse(config: dict, example_config: dict) -> dict:
    """
    Validate, parse, and/or compile the configurations for stages operations.

    Done for better speed when applying the same operations against multiple download
    items.

    :param config: The stages configuration from the Prunerr configuration.
    :param example_config: Prunerr's example configuration for defaults.
    :return: The operation configuration augmented with any pre-processing possible.
    :raises ValueError: There's something wrong with the configuration.
    """
    # Pull any missing stages and default operations from the examples:
    for stage, example_operations in example_config.items():
        if stage not in config:
            config.setdefault(stage, example_operations)
        for operation_name, example_operation in example_operations.items():
            if operation_name not in config[stage]:
                config[stage].setdefault(
                    operation_name,
                    example_operation,
                )

    if not isinstance(config, dict):
        raise ValueError(  # pragma: no cover
            f"Wrong stages YAML type: {type(config)}",
        )
    if not config:
        raise ValueError("Config is missing ``stages``")  # pragma: no cover
    if invalid_stages := set(config).difference(STAGES_SET):
        raise ValueError(  # pragma: no cover
            f"Config contains invalid stages: {list(invalid_stages)}",
        )

    for stage in STAGES:
        parse_stage(stage, config[stage])

    return config


def parse_stage(stage: str, stage_config: dict) -> dict:
    """
    Validate, parse, and/or compile the operations configurations for a stage.

    :param stage: The name of the download item life-cycle stage.
    :param stage_config: The operations configurations from the Prunerr configuration.
    :return: The operations configurations augmented with any pre-processing possible.
    :raises ValueError: There's something wrong with the configuration.
    """
    for operation_name in stage_config.keys():
        if (operation_config := stage_config[operation_name]) is None:
            # The user disabled a default operation:
            continue
        operation_config.setdefault("name", operation_name)

        if not ACTIONS.intersection(operation_config):
            raise ValueError(  # pragma: no cover
                f"Operation for {stage!r} missing action: {operation_name}"
            )

        operation_config.update(
            (key, jinja_env.from_string(operation_config[key]))
            for key in TEMPLATE_KEYS
            if key in operation_config and isinstance(operation_config[key], str)
        )
    return stage_config


class PrunerrStage(utils.PrunerrComponent):
    """
    A stage in the download item life-cycle and the operations to apply.
    """

    def __init__(
        self,
        name: str,
        config: dict,
        applier: utils.PrunerrComponent,
    ):
        """
        Capture references to the operation configs and the component applying them.
        """
        self.name = name
        self.config = config
        self.applier = applier

    def __call__(self) -> dict:
        """
        Apply the operations for this stage to the appliers items.
        """
        stage_results = {}
        break_applier = False
        for operation_name, operation_config in self.config.items():
            if operation_config is None:
                # The user disabled a default operation from the example configuration:
                continue

            operation = PrunerrOperation(self, operation_config)
            break_applier, operation_results = operation()
            if operation_results:
                stage_results[operation_name] = operation_results

            if break_applier:
                break

        return stage_results

    @property
    def details(self) -> dict:
        """
        Assemble all available useful information.

        :return: Map descriptive names to useful values.
        """
        return {"name": self.name, "applier": self.applier}

    @cached_property
    def items(self) -> list:
        """
        Retrieve the download items that are in this life-cycle stage.

        :return: The items to apply this stage's operations to.
        """
        stage_filter = getattr(
            self.applier,
            f"filter_{self.name.replace('-', '_')}",
        )
        if not (stage_items := list(stage_filter())):
            logger.debug("No items in %r", self)
        return stage_items


class PrunerrOperation(utils.PrunerrComponent):
    """
    An operation to apply to download items in a life-cycle stage.
    """

    def __init__(
        self,
        stage: PrunerrStage,
        config: dict,
    ):
        """
        Capture references to the stage and operation config.
        """
        self.stage = stage
        self.config = config

    def __call__(self) -> tuple:
        """
        Apply this stage operation to the appliers items.
        """
        operation_results = {}
        break_applier = False
        logger.debug("Applying %r", self)
        for item in self.items:
            item_results = None

            # Special case for orphaned files:
            if isinstance(self.items[0], utils.PrunerrOperationsItem):
                # Log messages specific to this download item to a dedicated log file:
                item.log_path.parent.mkdir(parents=True, exist_ok=True)
                item_handler = logging.FileHandler(item.log_path)
                item_handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
                root_logger.addHandler(item_handler)

            try:
                break_applier, item_results = self.apply_item(item)
            except CONTINUE_EXC_TYPES:
                logger.exception(
                    "Error applying %r to item: %r",
                    self,
                    item,
                )
            finally:
                if isinstance(self.items[0], utils.PrunerrOperationsItem):
                    root_logger.removeHandler(item_handler)
                    item_handler.acquire()
                    item_handler.flush()
                    item_handler.close()
            if item_results:
                if isinstance(self.items[0], utils.PrunerrOperationsItem):
                    operation_results[item.hashString] = item_results
                else:
                    operation_results[str(item)] = item_results

            if break_applier:
                break

        return break_applier, operation_results

    @property
    def details(self) -> dict:
        """
        Assemble all available useful information.

        :return: Map descriptive names to useful values.
        """
        return {"stage": self.stage.name, "name": self.config["name"]}

    @cached_property
    def items(self) -> list:
        """
        Filter and sort the items to apply this operation to.

        :return: The items to apply this operations to.
        """
        assemble_context = getattr(
            self.stage.applier,
            f"assemble_context_{self.config['name'].replace('-', '_')}",
            None,
        )
        operation_items = (
            # The configuration includes further filtering:
            [
                item
                for item in self.stage.items
                if self.config[OPERATION_INCLUDE].render(
                    **(
                        # Avoid an inner loop function call if possible:
                        {"item": item}
                        if assemble_context is None
                        else assemble_context(item)
                    ),
                )
            ]
            if OPERATION_INCLUDE in self.config
            # Need to make a copy in case actions lead to deleting an item and modifying
            # `download_client.items`:
            else list(self.stage.items)
        )
        if OPERATION_SORT in self.config:
            # The configuration specifies a sort:
            operation_items.sort(
                key=lambda item: self.config[OPERATION_SORT].render(
                    **(
                        # Avoid an inner loop function call if possible:
                        {"item": item}
                        if assemble_context is None
                        else assemble_context(item=item)
                    ),
                ),
            )

        if not operation_items:
            logger.debug("No items for %r", self)
        return operation_items

    def apply_item(
        self,
        item: typing.Union[utils.PrunerrComponent, pathlib.Path],
    ) -> tuple:
        """
        Apply the operations for this life-cycle stage to a download item.

        :param item: The item to apply the operations to. Usually this is a
            download item but is the file path for an orphaned file.
        :return: Map operation names to the actions taken if any.
        """
        break_applier = False
        action_args = (
            () if isinstance(self.items[0], utils.PrunerrOperationsItem) else (item,)
        )
        item_results = {}
        # Let the YAML key order dictate operation order:
        for action in self.config:
            if action not in ACTIONS:
                continue
            if OPERATION_BREAK in self.config and self.config[OPERATION_BREAK].render(
                item=item
            ):
                break_applier = True
                break

            action_apply = (
                getattr(item, f"apply_{action.replace('-', '_')}")
                if isinstance(
                    self.items[0],
                    utils.PrunerrOperationsItem,
                )
                else getattr(self.stage.applier, f"apply_{action.replace('-', '_')}")
            )
            logger.debug("Applying %r action: %s", self, action)
            if action_results := action_apply(self, *action_args):
                item_results.update(action_results)
            else:
                logger.debug(  # pragma: no cover
                    "No results for %r action: %s",
                    self,
                    action,
                )

        return break_applier, item_results


# Thanks to `homeassistant.helpers.template`:


def regex_match(value: str, find: str = "", ignorecase: bool = False) -> bool:
    """
    Match value using regex.

    :param value: The string to match against.
    :param find: The regular expression pattern.
    :param ignorecase: Whether to ignore case when matching.
    :return: Whether the pattern matched.
    """
    if not isinstance(value, str):
        value = str(value)  # pragma: no cover
    flags = re.I if ignorecase else 0
    return bool(_regex_cache(find, flags).match(value))


_regex_cache = functools.lru_cache(maxsize=128)(re.compile)


def regex_replace(
    value: str = "",
    find: str = "",
    replace: str = "",
    ignorecase: bool = False,
) -> str:  # pragma: no cover
    """
    Replace using regex.

    :param value: The string to match against.
    :param find: The regular expression pattern.
    :param replace: What to replace matches with.
    :param ignorecase: Whether to ignore case when matching.
    :return: The string with substitutions made.
    """
    if not isinstance(value, str):
        value = str(value)
    flags = re.I if ignorecase else 0
    return _regex_cache(find, flags).sub(replace, value)


def regex_search(
    value: str,
    find: str = "",
    ignorecase: bool = False,
) -> bool:  # pragma: no cover
    """
    Search using regex.

    :param value: The string to match against.
    :param find: The regular expression pattern.
    :param ignorecase: Whether to ignore case when matching.
    :return: Whether the pattern matched.
    """
    if not isinstance(value, str):
        value = str(value)
    flags = re.I if ignorecase else 0
    return bool(_regex_cache(find, flags).search(value))


def regex_findall_index(
    value: str,
    find: str = "",
    index: int = 0,
    ignorecase: bool = False,
) -> str:
    """
    Find all matches using regex and then pick specific match index.

    :param value: The string to match against.
    :param find: The regular expression pattern.
    :param index: The specific match to return.
    :param ignorecase: Whether to ignore case when matching.
    :return: The selected matching string.
    """
    return regex_findall(value, find, ignorecase)[index]  # pragma: no cover


def regex_findall(
    value: str,
    find: str = "",
    ignorecase: bool = False,
) -> list:  # pragma: no cover
    """
    Find all matches using regex.

    :param value: The string to match against.
    :param find: The regular expression pattern.
    :param ignorecase: Whether to ignore case when matching.
    :return: The matching string.
    """
    if not isinstance(value, str):
        value = str(value)
    flags = re.I if ignorecase else 0
    return _regex_cache(find, flags).findall(value)


jinja_env = jinja2.nativetypes.NativeEnvironment()
jinja_env.filters["regex_match"] = regex_match
jinja_env.filters["regex_replace"] = regex_replace
jinja_env.filters["regex_search"] = regex_search
jinja_env.filters["regex_findall"] = regex_findall
jinja_env.filters["regex_findall_index"] = regex_findall_index
jinja_env.tests["match"] = regex_match
jinja_env.tests["search"] = regex_search
