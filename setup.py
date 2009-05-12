#!/usr/bin/env python

from setuptools import setup

required = []
try:
    import json
except ImportError:
    required = ['simplejson>=1.7.1']

setup(
    name='transmissionrpc',
    version='0.3',
    description='Python module that implements the Transmission bittorent RPC protocol.',
    author='Erik Svensson',
    author_email='erik.public@gmail.com',
    url='http://bitbucket.org/blueluna/transmissionrpc',
    keywords='transmission bittorent torrent',
    packages=['transmissionrpc'],
    install_requires = required,
    test_suite = "tests",
    zip_safe=True,
    classifiers = [
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Topic :: Communications :: File Sharing',
        'Topic :: Internet'
        ],
    )
