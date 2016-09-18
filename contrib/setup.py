#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2008-2013 Erik Svensson <erik.public@gmail.com>
# Licensed under the MIT license.

from setuptools import setup

required = ['transmissionrpc', 'service-logging']

setup(
    name='transmissionrpc-contrib',
    version='0.11',
    description='Contributed tools built on the '
        'Python Transmission RPC library.',
    author='Erik Svensson',
    author_email='erik.public@gmail.com',
    url='https://bitbucket.org/blueluna/transmissionrpc/wiki/Helical',
    keywords='transmission bittorent torrent rpc',
    py_modules = ['helical'],
    install_requires = required,
    zip_safe=True,
    classifiers = [
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Topic :: Communications :: File Sharing',
        'Topic :: Internet'
        ],
    entry_points={
        'console_scripts': ['helical=helical:main'],
        },
    )
