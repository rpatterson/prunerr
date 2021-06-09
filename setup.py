#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Remove Servarr download client items to preserve disk space according to rules.
"""

from setuptools import setup

required = [
    # Specific download client APIs
    transmission=["transmission-rpc"],
    # Graceful handling of logging when run on the console or as a daemon
    "service-logging",
    # Configuration file format
    "pyyaml",
]

setup(
    name="prunerr",
    version="0.1",
    description=__doc__.strip(),
    author="Ross Patterson",
    author_email="me@rpatterson.net",
    url="https://gitlab.com/rpatterson/transmissionrpc",
    keywords="servarr sonarr radarr transmission bittorent torrent",
    py_modules=["prunerr"],
    install_requires=required,
    zip_safe=True,
    classifiers=[
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Topic :: Communications :: File Sharing",
        "Topic :: Internet",
    ],
    entry_points={"console_scripts": ["prunerr=prunerr:main"],},
)
