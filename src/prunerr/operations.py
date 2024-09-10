# SPDX-FileCopyrightText: 2023 Ross Patterson <me@rpatterson.net>
# SPDX-License-Identifier: MIT

"""
Download item metadata operations used in Prunerr configuration.

Used to determine item indexer priority, reviewing grabbed items, etc.
"""

import functools
import re
import logging

import jinja2.environment
import jinja2.nativetypes

logger = logging.getLogger(__name__)

CONFIG_INCLUDE_KEY = "include"
CONFIG_SORT_KEY = "sort"


def parse(config: dict) -> dict:
    """
    Parse or compile any expressions in the operations configurations.

    Done for better speed when executing the same operation against multiple download
    items.

    :param config: The operations configuration from the Prunerr configuration.
    :return: The operation configuration augmented with any pre-processing possible.
    """
    for operation_config in tuple(config.get("reviews", {}).values()) + (
        config.get("free-space", {}),
    ):
        operation_config.update(
            (key, jinja_env.from_string(operation_config[key]))
            for key in (CONFIG_INCLUDE_KEY, CONFIG_SORT_KEY)
            if key in operation_config and isinstance(operation_config[key], str)
        )
    return config


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
