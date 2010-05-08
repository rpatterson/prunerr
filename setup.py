#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2008-2010 Erik Svensson <erik.public@gmail.com>
# Licensed under the MIT license.

from setuptools import setup

required = []
try:
    import json
except ImportError:
    required = ['simplejson>=1.7.1']

setup(
    name='transmissionrpc',
    version='0.5',
    description='Python module that implements the Transmission bittorent client RPC protocol.',
    author='Erik Svensson',
    author_email='erik.public@gmail.com',
    url='http://bitbucket.org/blueluna/transmissionrpc',
    keywords='transmission bittorent torrent',
    packages=['transmissionrpc'],
    install_requires = required,
    test_suite = "test",
    zip_safe=True,
    classifiers = [
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Topic :: Communications :: File Sharing',
        'Topic :: Internet'
        ],
    )
